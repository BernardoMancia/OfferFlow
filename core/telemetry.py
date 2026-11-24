from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from config import BASE_DIR, settings
from database.logger import get_logger

logger = get_logger("core.telemetry")
_STARTED_AT = time.time()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_health_payload(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": "ok",
        "app_name": settings.project_name,
        "version": settings.app_version,
        "environment": settings.app_environment,
        "uptime_sec": int(time.time() - _STARTED_AT),
        "timestamp": _utc_now(),
    }
    if extra:
        payload.update(extra)
    return payload


def write_app_manifest() -> Optional[Path]:
    raw_manifest = settings.central_manifest_path
    if not raw_manifest:
        return None
    manifest_path = Path(raw_manifest)
    manifest: Dict[str, Any] = {
        "schema_version": "2.0",
        "app_name": settings.project_name,
        "version": settings.app_version,
        "runtime": settings.app_runtime,
        "service_name": settings.app_service_name or settings.project_name,
        "owner_user": settings.app_owner_user,
        "port": settings.web_port,
        "health_url": settings.health_url or f"http://127.0.0.1:{settings.web_port}/health",
        "environment": settings.app_environment,
        "logs_db_path": str(settings.log_db_path),
        "protected": settings.app_protected,
        "pid": os.getpid(),
        "updated_at": _utc_now(),
        "sbom_files": [str(BASE_DIR / "requirements.txt")],
        "sensitive_paths": [str(BASE_DIR / ".env")],
        "expected_outbound_hosts": [
            "api.telegram.org",
            "www.mercadolivre.com.br",
            "api.mercadolibre.com",
            "www.pelando.com.br",
            "www.promobit.com.br",
            "gatry.com",
        ],
    }
    tmp_path: Optional[str] = None
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(manifest, indent=2, ensure_ascii=False)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(manifest_path.parent),
            prefix=".central-app-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            tmp_path = handle.name
        os.replace(tmp_path, str(manifest_path))
        return manifest_path
    except Exception as exc:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        logger.debug(f"Não foi possível gravar manifesto da Central: {exc}")
        return None


async def _post_central_json(path: str, body: Dict[str, Any]) -> bool:
    api_url = settings.central_api_url.rstrip("/")
    token = settings.central_app_token
    if not api_url or not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{api_url}{path}",
                json=body,
                headers={"X-App-Token": token},
            )
            return 200 <= resp.status_code < 300
    except Exception:
        return False


async def send_heartbeat() -> bool:
    await asyncio.to_thread(write_app_manifest)
    return await _post_central_json(
        "/api/v1/sdk/heartbeat",
        {"version": settings.app_version, "status": "ok"},
    )


async def report_central_event(
    level: str,
    source: str,
    message: str,
    trigger_alert: bool = False,
    title: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    body = {
        "level": (level or "INFO").upper(),
        "source": str(source or settings.project_name),
        "message": str(message),
        "trigger_alert": bool(trigger_alert),
        "title": str(title or ""),
        "metadata": {str(k): str(v) for k, v in (metadata or {}).items()},
    }
    return await _post_central_json("/api/v1/sdk/event", body)

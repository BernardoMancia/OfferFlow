from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse, urlunparse

from affiliate.amazon import _resolve_setting
from affiliate.url_cleaner import clean_store_url
from config import settings


def build_magalu_affiliate_url(
    clean_url: str,
    magalu_slug: Optional[str] = None,
) -> str:
    normalized = clean_store_url(clean_url)
    if not normalized:
        return clean_url

    slug = _resolve_setting(
        magalu_slug, settings.magalu_store_slug, "magalu_store_slug", magalu_slug is None
    ).strip("/")
    if not slug or slug == "SUA_LOJA_MAGALU":
        return normalized

    parsed = urlparse(normalized)
    host = parsed.netloc.lower()
    if "magazineluiza.com.br" not in host and "magazinevoce.com.br" not in host:
        return normalized

    path = parsed.path or "/"
    if "magazinevoce.com.br" in host:
        parts = [p for p in path.split("/") if p]
        if parts:
            parts[0] = slug
            new_path = "/" + "/".join(parts) + ("/" if path.endswith("/") else "")
        else:
            new_path = f"/{slug}/"
    else:
        new_path = f"/{slug}{path if path.startswith('/') else '/' + path}"

    return urlunparse(
        ("https", "www.magazinevoce.com.br", new_path, "", "", "")
    )

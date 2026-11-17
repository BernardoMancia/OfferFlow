from __future__ import annotations

import ast
import io
import pathlib
import re
import sqlite3
import tokenize

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
IGNORED_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "venv",
    ".venv",
    "ENV",
    "data",
    "logs",
    "backups",
}
IGNORED_FILES = {
    ".env",
    "HISTORICO_VERSOES_E_BACKUPS.md",
}


def _iter_repo_files() -> list[pathlib.Path]:
    result: list[pathlib.Path] = []
    for path in sorted(ROOT_DIR.rglob("*")):
        if path.is_dir():
            continue
        rel_parts = set(path.relative_to(ROOT_DIR).parts)
        if rel_parts & IGNORED_DIRS:
            continue
        if path.name in IGNORED_FILES:
            continue
        if path.suffix in (".db", ".db-wal", ".db-shm", ".db-journal", ".pyc", ".log", ".zip"):
            continue
        result.append(path)
    return result


def test_zero_comments_and_docstrings_in_python_files() -> None:
    for path in _iter_repo_files():
        if path.suffix != ".py":
            continue
        src = path.read_text(encoding="utf-8")
        tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))
        comments = [t for t in tokens if t.type == tokenize.COMMENT]
        assert not comments, f"Comentário encontrado em {path.relative_to(ROOT_DIR)}: linha {comments[0].start[0]}"

        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                assert doc is None, f"Docstring encontrada em {path.relative_to(ROOT_DIR)}"


def test_no_sensitive_data_or_vps_metadata_leaks() -> None:
    forbidden_patterns = [
        r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b",
        r"(?<!\d)-100\d{7,}(?!\d)",
        r"82\.112\.245\.99",
        r"SRV-AUTOMACAO",
        r"LOGS-PROJETOS",
        r"promoooow",
    ]

    secret_literals: list[str] = []
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "ML_AFFILIATE_COOKIE", "ML_CSRF_TOKEN", "SHOPEE_APP_SECRET"):
                if v and v not in ("SEU_TOKEN_AQUI", "SEU_MATT_TOOL", "SEU_MATT_WORD", "SUA_TAG_DE_AFILIADO"):
                    secret_literals.append(v)

    db_file = ROOT_DIR / "data" / "bot.db"
    if db_file.exists():
        conn = sqlite3.connect(str(db_file))
        try:
            rows = conn.execute(
                "SELECT key, value FROM bot_config WHERE key IN ('chat_id', 'group_url', 'group_username', 'admin_private_chat_id', 'ml_affiliate_cookie')"
            ).fetchall()
            for _, val in rows:
                if val and len(str(val).strip()) >= 4:
                    secret_literals.append(str(val).strip())
        finally:
            conn.close()

    for path in _iter_repo_files():
        if path.name == "test_security_no_leaks.py":
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT_DIR).as_posix()
        for pat in forbidden_patterns:
            match = re.search(pat, content, flags=re.IGNORECASE)
            assert match is None, f"Padrão proibido ({pat}) detectado em {rel}"
        for secret in secret_literals:
            assert secret not in content, f"Vazamento de segredo real detectado em {rel}"

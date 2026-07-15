"""Environment configuration helpers."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_env_file() -> None:
    """Load local/project env files without overriding process environment."""
    current = Path(__file__).resolve()
    env_root = None
    for parent in current.parents:
        candidate = parent / ".env"
        if candidate.exists():
            env_root = parent
            break
    if env_root is None:
        return
    for env_path in (env_root / ".env.local", env_root / ".env"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_bool(name: str, default: bool = False) -> bool:
    load_env_file()
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_str(name: str, default: str = "") -> str:
    load_env_file()
    value = os.getenv(name)
    if value is not None:
        return value.strip()
    secret_path = os.getenv(f"{name}_FILE", "").strip()
    if secret_path:
        try:
            return Path(secret_path).read_text(encoding="utf-8").strip()
        except OSError:
            return default
    return default.strip()


def env_int(name: str, default: int = 0) -> int:
    load_env_file()
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def database_url() -> str:
    if env_bool("WCPA_DISABLE_DATABASE", False):
        return ""
    configured = env_str("WCPA_DATABASE_URL", "")
    composed = _postgres_url_from_parts()
    if configured:
        expanded = _expand_env_placeholders(configured)
        if _looks_like_legacy_local_default(expanded) and composed:
            return composed
        return expanded
    return composed


def _postgres_url_from_parts() -> str:
    db = env_str("WCPA_POSTGRES_DB", "wcpa")
    user = env_str("WCPA_POSTGRES_USER", "postgre")
    password = env_str("WCPA_POSTGRES_PASSWORD", "postgre")
    host = env_str("WCPA_POSTGRES_HOST", "127.0.0.1")
    port = env_str("WCPA_POSTGRES_PORT", "5432")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _expand_env_placeholders(value: str) -> str:
    pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-[^}]*)?\}")

    def replace(match: re.Match[str]) -> str:
        expression = match.group(0)[2:-1]
        if ":-" in expression:
            name, default = expression.split(":-", 1)
        else:
            name, default = expression, ""
        return env_str(name, default)

    return pattern.sub(replace, value)


def _looks_like_legacy_local_default(value: str) -> bool:
    return "://wcpa:wcpa@localhost:" in value

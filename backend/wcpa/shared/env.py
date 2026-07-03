"""Environment configuration helpers."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_env_file() -> None:
    """Load project .env without overriding process environment."""
    current = Path(__file__).resolve()
    env_path = None
    for parent in current.parents:
        candidate = parent / ".env"
        if candidate.exists():
            env_path = candidate
            break
    if env_path is None:
        return
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
    return os.getenv(name, default).strip()


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
    return env_str("WCPA_DATABASE_URL", "")

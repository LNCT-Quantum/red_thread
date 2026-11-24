"""Runtime configuration, read from environment variables (never hard-coded URLs)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

__all__ = ["API_PREFIX", "API_VERSION", "SERVICE_NAME", "Settings"]

API_VERSION = "1.0.0"
API_PREFIX = "/api/v1"
SERVICE_NAME = "red-thread-backend"


def _split(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _read_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean (true/false), got {raw!r}.")


def _read_number(env: Mapping[str, str], name: str, default: float, minimum: float, cast=float):
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = cast(raw.strip())
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}.") from None
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {value}.")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """All API settings. Every field has an ``API_*`` environment variable."""

    #: ``API_CORS_ORIGINS`` - comma separated allowed browser origins. Empty = no CORS headers.
    cors_origins: tuple[str, ...] = ()
    #: ``API_CASE_IDS`` - comma separated cases to load. ``None`` = every case found on disk.
    case_ids: tuple[str, ...] | None = None
    #: ``API_CASE_DATA_ROOT`` - override of the ``case_data`` directory.
    case_data_root: Path | None = None
    #: ``API_DIALOGUE_TIMEOUT_S`` - hard cap on one NPC reply (the LLM engine has its own
    #: finer-grained ``LLM_*`` timeouts; this is the API-level safety net).
    dialogue_timeout_s: float = 150.0
    #: ``API_LLM_CONCURRENCY`` - simultaneous LLM generations across all players.
    llm_concurrency: int = 2
    #: ``API_INTERVIEW_MIN_TURNS`` - NPC replies required before an interview may be completed.
    interview_min_turns: int = 1
    #: ``API_MAX_BODY_BYTES`` - request bodies larger than this are refused with 413.
    max_body_bytes: int = 16_384
    #: ``API_ENABLE_DOCS`` - serve OpenAPI/Swagger at ``/api/v1/docs``.
    enable_docs: bool = True
    #: ``API_LOG_LEVEL`` - Python log level name.
    log_level: str = "INFO"
    #: ``API_HOST`` / ``API_PORT`` - used only by ``python main.py``.
    host: str = "127.0.0.1"
    port: int = 8000

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        case_ids = _split(env.get("API_CASE_IDS", ""))
        root = env.get("API_CASE_DATA_ROOT", "").strip()
        return cls(
            cors_origins=_split(env.get("API_CORS_ORIGINS", "")),
            case_ids=case_ids or None,
            case_data_root=Path(root) if root else None,
            dialogue_timeout_s=_read_number(env, "API_DIALOGUE_TIMEOUT_S", 150.0, 1.0),
            llm_concurrency=int(_read_number(env, "API_LLM_CONCURRENCY", 2, 1, cast=int)),
            interview_min_turns=int(_read_number(env, "API_INTERVIEW_MIN_TURNS", 1, 0, cast=int)),
            max_body_bytes=int(_read_number(env, "API_MAX_BODY_BYTES", 16_384, 1024, cast=int)),
            enable_docs=_read_bool(env, "API_ENABLE_DOCS", True),
            log_level=env.get("API_LOG_LEVEL", "INFO").strip().upper() or "INFO",
            host=env.get("API_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=int(_read_number(env, "API_PORT", 8000, 1, cast=int)),
        )

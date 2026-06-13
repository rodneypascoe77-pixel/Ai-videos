"""Central configuration — loads .env and validates required secrets.

Fails loudly at import/use time if a required key is missing, so misconfiguration
surfaces immediately rather than deep inside an API call.

Usage:
    from config import settings
    settings.YOUTUBE_API_KEY
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root = two levels up from this file (src/config.py -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

# Load .env from the project root if present
load_dotenv(PROJECT_ROOT / ".env")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _require(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise ConfigError(
            f"Missing required environment variable: {key!r}.\n"
            f"  -> Add it to your .env file at {PROJECT_ROOT / '.env'}\n"
            f"  -> See .env.example for the full list of required keys."
        )
    return value


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


@dataclass(frozen=True)
class Settings:
    # Required secrets — accessed lazily via validate() / properties
    YOUTUBE_API_KEY: str
    ANTHROPIC_API_KEY: str

    # Optional / has-default settings
    DATABASE_URL: str
    ANTHROPIC_MODEL: str
    LOG_LEVEL: str
    DISCOVERY_INTERVAL_HOURS: float

    # Phase 3 — video generation
    RUNWAY_API_KEY: str        # only required when OFFLINE_MODE is false
    OFFLINE_MODE: bool         # true = stub providers (free); false = real APIs
    VIDEO_MODEL: str
    VIDEO_IMAGE_MODEL: str
    VIDEO_RATIO: str
    VIDEO_DURATION: int

    # Phase 5 — YouTube posting
    POST_INTERVAL_HOURS: float
    YOUTUBE_PRIVACY: str           # private | unlisted | public
    YOUTUBE_CLIENT_SECRETS: str    # path to OAuth client_secret.json
    YOUTUBE_TOKEN_FILE: str        # path to saved OAuth token

    # Phase 7 — feedback loop
    FEEDBACK_INTERVAL_HOURS: float

    @classmethod
    def load(cls) -> "Settings":
        """Build Settings, raising ConfigError if any required key is missing."""
        return cls(
            YOUTUBE_API_KEY=_require("YOUTUBE_API_KEY"),
            ANTHROPIC_API_KEY=_require("ANTHROPIC_API_KEY"),
            DATABASE_URL=_optional("DATABASE_URL", f"sqlite:///{DATA_DIR / 'pipeline.db'}"),
            ANTHROPIC_MODEL=_optional("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            LOG_LEVEL=_optional("LOG_LEVEL", "INFO"),
            DISCOVERY_INTERVAL_HOURS=float(_optional("DISCOVERY_INTERVAL_HOURS", "4")),
            RUNWAY_API_KEY=_optional("RUNWAY_API_KEY"),
            OFFLINE_MODE=_optional("OFFLINE_MODE", "true").lower() in ("1", "true", "yes"),
            VIDEO_MODEL=_optional("VIDEO_MODEL", "gen4.5"),
            VIDEO_IMAGE_MODEL=_optional("VIDEO_IMAGE_MODEL", "gen4_image"),
            VIDEO_RATIO=_optional("VIDEO_RATIO", "1280:720"),
            VIDEO_DURATION=int(_optional("VIDEO_DURATION", "5")),
            POST_INTERVAL_HOURS=float(_optional("POST_INTERVAL_HOURS", "8")),
            YOUTUBE_PRIVACY=_optional("YOUTUBE_PRIVACY", "private"),
            YOUTUBE_CLIENT_SECRETS=_optional(
                "YOUTUBE_CLIENT_SECRETS", str(PROJECT_ROOT / "secrets" / "client_secret.json")
            ),
            YOUTUBE_TOKEN_FILE=_optional(
                "YOUTUBE_TOKEN_FILE", str(PROJECT_ROOT / "secrets" / "youtube_token.json")
            ),
            FEEDBACK_INTERVAL_HOURS=float(_optional("FEEDBACK_INTERVAL_HOURS", "12")),
        )


def get_settings() -> Settings:
    """Load and validate settings. Call this where you actually need the keys."""
    return Settings.load()


if __name__ == "__main__":
    try:
        s = get_settings()
    except ConfigError as exc:
        print(f"[CONFIG ERROR]\n{exc}")
        raise SystemExit(1)
    print("Configuration OK.")
    print(f"  Model:        {s.ANTHROPIC_MODEL}")
    print(f"  Database URL: {s.DATABASE_URL}")
    print(f"  Log level:    {s.LOG_LEVEL}")
    print(f"  YOUTUBE_API_KEY:   {'set' if s.YOUTUBE_API_KEY else 'MISSING'}")
    print(f"  ANTHROPIC_API_KEY: {'set' if s.ANTHROPIC_API_KEY else 'MISSING'}")

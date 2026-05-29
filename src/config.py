"""Centralised configuration for FanSphere AI.

All environment-driven settings, logging, and the SQLAlchemy engine live here so
the rest of the codebase imports a single, consistent object.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
OUTPUTS_DIR = ROOT_DIR / "outputs"
DATA_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv(ROOT_DIR / ".env")


def _csv_env(key: str, default: str = "") -> List[str]:
    raw = os.getenv(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Strongly-typed view of environment configuration."""

    # Postgres
    pg_host: str = os.getenv("POSTGRES_HOST", "localhost")
    pg_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    pg_db: str = os.getenv("POSTGRES_DB", "fansphere_ai")
    pg_user: str = os.getenv("POSTGRES_USER", "fansphere")
    pg_password: str = os.getenv("POSTGRES_PASSWORD", "")

    # Reddit
    reddit_client_id: str = os.getenv("REDDIT_CLIENT_ID", "")
    reddit_client_secret: str = os.getenv("REDDIT_CLIENT_SECRET", "")
    reddit_user_agent: str = os.getenv("REDDIT_USER_AGENT", "fansphere-ai/0.1")
    reddit_post_limit: int = int(os.getenv("REDDIT_POST_LIMIT", "100"))
    reddit_comment_limit: int = int(os.getenv("REDDIT_COMMENT_LIMIT", "50"))

    # Lists
    subreddits: List[str] = field(
        default_factory=lambda: _csv_env("REDDIT_SUBREDDITS", "Barca,soccer")
    )
    statsbomb_competition_ids: List[int] = field(
        default_factory=lambda: [int(x) for x in _csv_env("STATSBOMB_COMPETITION_IDS", "11")]
    )

    @property
    def db_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )


SETTINGS = Settings()


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def get_engine() -> Engine:
    """Return a lazily-created SQLAlchemy engine."""
    return create_engine(SETTINGS.db_url, pool_pre_ping=True, future=True)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def get_logger(name: str) -> logging.Logger:
    """Module-level logger with a consistent format."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger

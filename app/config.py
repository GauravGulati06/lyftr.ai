import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    webhook_secret: str | None
    log_level: str


def load_settings() -> Settings:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    webhook_secret = os.environ.get("WEBHOOK_SECRET", "").strip() or None
    log_level = os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    return Settings(database_url=database_url, webhook_secret=webhook_secret, log_level=log_level)


def sqlite_path_from_url(database_url: str) -> str:
    if database_url == "sqlite:///:memory:":
        return ":memory:"
    if not database_url.startswith("sqlite:///"):
        raise RuntimeError("DATABASE_URL must start with sqlite:///")
    return database_url[len("sqlite:///"):]

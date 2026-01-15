import json
import logging
from datetime import datetime, timezone


def configure_logging(level: str) -> logging.Logger:
    logging.basicConfig(level=getattr(logging, level, logging.INFO), format="%(message)s")
    return logging.getLogger("app")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def log_json(logger: logging.Logger, level: int, payload: dict) -> None:
    if "ts" not in payload:
        payload = {"ts": now_iso(), **payload}
    payload = {**payload, "level": logging.getLevelName(level)}
    logger.log(level, json.dumps(payload, separators=(",", ":"), ensure_ascii=False))

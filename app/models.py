import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


_E164_RE = re.compile(r"^\+[0-9]+$")


def _validate_utc_z(v: str) -> str:
    if not isinstance(v, str) or not v.endswith("Z"):
        raise ValueError("ts must be an ISO-8601 UTC timestamp with Z suffix")
    dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if dt.utcoffset() is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError("ts must be UTC")
    return v


class MessageIn(BaseModel):
    message_id: str = Field(min_length=1)
    from_msisdn: str = Field(alias="from")
    to_msisdn: str = Field(alias="to")
    ts: str
    text: str | None = Field(default=None, max_length=4096)

    model_config = {"populate_by_name": True}

    @field_validator("from_msisdn")
    @classmethod
    def validate_from(cls, v: str) -> str:
        if not isinstance(v, str) or not _E164_RE.match(v):
            raise ValueError("from must be in E.164-like format")
        return v

    @field_validator("to_msisdn")
    @classmethod
    def validate_to(cls, v: str) -> str:
        if not isinstance(v, str) or not _E164_RE.match(v):
            raise ValueError("to must be in E.164-like format")
        return v

    @field_validator("ts")
    @classmethod
    def validate_ts(cls, v: str) -> str:
        return _validate_utc_z(v)


class MessageOut(BaseModel):
    message_id: str
    from_msisdn: str = Field(alias="from")
    to_msisdn: str = Field(alias="to")
    ts: str
    text: str | None

    model_config = {"populate_by_name": True}


class MessagesResponse(BaseModel):
    data: list[MessageOut]
    total: int
    limit: int
    offset: int


class WebhookOk(BaseModel):
    status: str


class StatsResponse(BaseModel):
    total_messages: int
    senders_count: int
    messages_per_sender: list[dict]
    first_message_ts: str | None
    last_message_ts: str | None

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient


def _sig(secret: str, body: str) -> str:
    return hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBHOOK_SECRET", "testsecret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    from app.main import create_app

    app = create_app()
    return TestClient(app)


def _post(client: TestClient, payload: dict):
    body = json.dumps(payload)
    sig = _sig("testsecret", body)
    r = client.post(
        "/webhook",
        data=body,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )
    assert r.status_code == 200


def test_stats_correctness(client: TestClient):
    _post(
        client,
        {
            "message_id": "m1",
            "from": "+919876543210",
            "to": "+14155550100",
            "ts": "2025-01-15T10:00:00Z",
            "text": "Hello",
        },
    )
    _post(
        client,
        {
            "message_id": "m2",
            "from": "+919876543210",
            "to": "+14155550100",
            "ts": "2025-01-15T11:00:00Z",
            "text": "Hello again",
        },
    )
    _post(
        client,
        {
            "message_id": "m3",
            "from": "+911234567890",
            "to": "+14155550100",
            "ts": "2025-01-14T10:00:00Z",
            "text": "Earlier",
        },
    )

    r = client.get("/stats")
    assert r.status_code == 200
    body = r.json()

    assert body["total_messages"] == 3
    assert body["senders_count"] == 2
    assert body["first_message_ts"] == "2025-01-14T10:00:00Z"
    assert body["last_message_ts"] == "2025-01-15T11:00:00Z"

    top = body["messages_per_sender"]
    assert top[0]["from"] == "+919876543210"
    assert top[0]["count"] == 2

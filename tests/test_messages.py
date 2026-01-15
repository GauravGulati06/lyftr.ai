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


def test_pagination_filters_ordering(client: TestClient):
    _post(
        client,
        {
            "message_id": "m2",
            "from": "+919876543210",
            "to": "+14155550100",
            "ts": "2025-01-15T09:00:00Z",
            "text": "Earlier",
        },
    )
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
            "message_id": "m3",
            "from": "+911234567890",
            "to": "+14155550100",
            "ts": "2025-01-15T11:00:00Z",
            "text": "Later",
        },
    )

    r = client.get("/messages?limit=2&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert body["total"] == 3
    assert len(body["data"]) == 2
    assert body["data"][0]["message_id"] == "m2"
    assert body["data"][1]["message_id"] == "m1"

    r2 = client.get("/messages?from=+911234567890")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["total"] == 1
    assert body2["data"][0]["message_id"] == "m3"

    r3 = client.get("/messages?since=2025-01-15T10:00:00Z")
    assert r3.status_code == 200
    body3 = r3.json()
    assert body3["total"] == 2

    r4 = client.get("/messages?q=hello")
    assert r4.status_code == 200
    body4 = r4.json()
    assert body4["total"] == 1
    assert body4["data"][0]["message_id"] == "m1"

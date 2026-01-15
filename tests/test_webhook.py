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


def test_invalid_signature_401(client: TestClient):
    body = json.dumps(
        {
            "message_id": "m1",
            "from": "+919876543210",
            "to": "+14155550100",
            "ts": "2025-01-15T10:00:00Z",
            "text": "Hello",
        }
    )
    r = client.post(
        "/webhook",
        data=body,
        headers={"Content-Type": "application/json", "X-Signature": "123"},
    )
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid signature"}


def test_valid_insert_and_duplicate_idempotent(client: TestClient):
    body = json.dumps(
        {
            "message_id": "m1",
            "from": "+919876543210",
            "to": "+14155550100",
            "ts": "2025-01-15T10:00:00Z",
            "text": "Hello",
        }
    )
    sig = _sig("testsecret", body)

    r1 = client.post(
        "/webhook",
        data=body,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )
    assert r1.status_code == 200
    assert r1.json() == {"status": "ok"}

    r2 = client.post(
        "/webhook",
        data=body,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )
    assert r2.status_code == 200
    assert r2.json() == {"status": "ok"}

    r3 = client.get("/messages")
    assert r3.status_code == 200
    assert r3.json()["total"] == 1

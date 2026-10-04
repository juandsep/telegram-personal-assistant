# Minimal smoke test: the one service imports and exposes its routes.

from fastapi.testclient import TestClient

from assistant.app import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/health").status_code == 200


def test_webhook_rejects_missing_secret() -> None:
    assert client.post("/tg/whatever").status_code == 403


def test_google_routes_need_a_token() -> None:
    # The service is public: without the OIDC token these never run.
    assert client.post("/push", json={}).status_code == 403
    assert client.post("/tasks/reminder", json={}).status_code == 403

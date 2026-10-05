import dataclasses
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from google.oauth2 import id_token

from assistant import authz
from assistant.app import app
from assistant.config import get_worker_settings

URL = "https://assistant.example"
SA = "assistant-worker@p.iam.gserviceaccount.com"
client = TestClient(app)
BEARER = {"Authorization": "Bearer t0k3n"}


@pytest.fixture
def verify(monkeypatch):
    s = dataclasses.replace(get_worker_settings(), worker_url=URL, worker_sa=SA)
    monkeypatch.setattr(authz, "get_worker_settings", lambda: s)
    m = MagicMock(return_value={"email": SA, "email_verified": True})
    monkeypatch.setattr(id_token, "verify_oauth2_token", m)
    return m


def test_valid_google_token_reaches_the_route(verify) -> None:
    # A junk body behind a good token is acked (204), proving the gate passed.
    assert client.post("/push", content=b"junk", headers=BEARER).status_code == 204
    assert verify.call_args.args[0] == "t0k3n"
    assert verify.call_args.kwargs == {"audience": URL}
    assert (
        client.post("/tasks/reminder", content=b"x", headers=BEARER).status_code == 204
    )


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "t0k3n"}, {"Authorization": "Bearer "}]
)
def test_missing_token_is_refused(verify, headers) -> None:
    assert client.post("/push", content=b"{}", headers=headers).status_code == 403
    verify.assert_not_called()


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "other@p.iam.gserviceaccount.com", "email_verified": True},
        {"email": SA, "email_verified": False},
        {},
    ],
)
def test_token_for_another_caller_is_refused(verify, claims) -> None:
    verify.return_value = claims
    assert client.post("/push", content=b"{}", headers=BEARER).status_code == 403


def test_invalid_token_is_refused(verify) -> None:
    verify.side_effect = ValueError("wrong audience")
    assert client.post("/push", content=b"{}", headers=BEARER).status_code == 403


def test_unconfigured_service_fails_closed(verify, monkeypatch) -> None:
    unset = dataclasses.replace(get_worker_settings(), worker_url="", worker_sa=SA)
    monkeypatch.setattr(authz, "get_worker_settings", lambda: unset)
    assert client.post("/push", content=b"{}", headers=BEARER).status_code == 403
    verify.assert_not_called()


def test_public_routes_need_no_token() -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/visor").status_code == 200

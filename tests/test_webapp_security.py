"""Web app startup secret check and session cookie flags, without a database."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from job_aggregator.config import settings
from job_aggregator.webapp import app as app_module
from job_aggregator.webapp.auth import COOKIE_NAME, hash_password

ROOT = Path(__file__).resolve().parent.parent
GOOD_SECRET = "x" * 48


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    async def _noop() -> None:
        return None

    monkeypatch.setattr(app_module, "init_db", _noop)


def _env_example_value(name: str) -> str:
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1]
    raise AssertionError(f"{name} not found in .env.example")


# ── Startup secret check ─────────────────────────────────────────────


@pytest.mark.parametrize("secret", ["", "   "])
def test_web_app_refuses_to_start_without_secret(monkeypatch, secret) -> None:
    monkeypatch.setattr(settings, "webapp_secret", secret)
    with pytest.raises(RuntimeError, match="WEBAPP_SECRET"), TestClient(app_module.app):
        pass


def test_web_app_refuses_to_start_with_env_example_placeholder(monkeypatch) -> None:
    monkeypatch.setattr(settings, "webapp_secret", _env_example_value("WEBAPP_SECRET"))
    with pytest.raises(RuntimeError, match="WEBAPP_SECRET"), TestClient(app_module.app):
        pass


def test_web_app_starts_with_a_real_secret(monkeypatch) -> None:
    monkeypatch.setattr(settings, "webapp_secret", GOOD_SECRET)
    with TestClient(app_module.app) as client:
        assert client.get("/login").status_code == 200


# ── Session cookie flags ─────────────────────────────────────────────


class _Result:
    def __init__(self, user) -> None:
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class _Session:
    def __init__(self, user) -> None:
        self._user = user

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def execute(self, _stmt):
        return _Result(self._user)


@pytest.fixture
def login_client(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4(), hashed_password=hash_password("correct-horse"))

    async def _touch(_user_id) -> None:
        return None

    monkeypatch.setattr(settings, "webapp_secret", GOOD_SECRET)
    monkeypatch.setattr("job_aggregator.db.engine.async_session", lambda: _Session(user))
    monkeypatch.setattr(app_module, "touch_last_login", _touch)
    # No `with`: the lifespan (secret check, init_db) is not under test here.
    return TestClient(app_module.app)


def _login_set_cookie(client: TestClient) -> str:
    resp = client.post(
        "/login",
        data={"username": "admin", "password": "correct-horse"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    cookies = [c for c in resp.headers.get_list("set-cookie") if c.startswith(f"{COOKIE_NAME}=")]
    assert len(cookies) == 1
    return cookies[0].lower()


def test_session_cookie_is_secure_by_default(login_client) -> None:
    cookie = _login_set_cookie(login_client)
    assert "; secure" in cookie
    assert "; httponly" in cookie
    assert "samesite=lax" in cookie


def test_insecure_cookie_opt_out_for_local_http(monkeypatch, login_client) -> None:
    monkeypatch.setattr(settings, "webapp_insecure_cookies", True)
    cookie = _login_set_cookie(login_client)
    assert "; secure" not in cookie
    assert "; httponly" in cookie


def test_insecure_cookie_opt_out_is_documented_in_env_example() -> None:
    assert _env_example_value("WEBAPP_INSECURE_COOKIES").strip().lower() in {"false", ""}

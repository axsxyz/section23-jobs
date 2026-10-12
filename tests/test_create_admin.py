"""Password input of scripts/create_admin.py, without a database."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "create_admin.py"


@pytest.fixture
def script(monkeypatch):
    spec = importlib.util.spec_from_file_location("create_admin", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    calls: list[tuple[str, str]] = []

    async def _fake_create_admin(username: str, password: str) -> None:
        calls.append((username, password))

    monkeypatch.setattr(module, "create_admin", _fake_create_admin)
    module.calls = calls
    return module


def test_password_is_prompted_without_echo(script, monkeypatch, capsys) -> None:
    prompts: list[str] = []

    def _fake_getpass(prompt: str = "") -> str:
        prompts.append(prompt)
        return "s3cret-pass"

    monkeypatch.setattr(script.getpass, "getpass", _fake_getpass)

    script.main(["create_admin.py", "admin"])

    assert script.calls == [("admin", "s3cret-pass")]
    assert len(prompts) == 2  # password + confirmation
    assert "s3cret-pass" not in capsys.readouterr().out


def test_mismatched_confirmation_aborts(script, monkeypatch) -> None:
    answers = iter(["first-password", "other-password"])
    monkeypatch.setattr(script.getpass, "getpass", lambda prompt="": next(answers))

    with pytest.raises(SystemExit):
        script.main(["create_admin.py", "admin"])
    assert script.calls == []


def test_password_on_command_line_still_works_with_a_warning(script, capsys) -> None:
    script.main(["create_admin.py", "admin", "argv-password"])

    assert script.calls == [("admin", "argv-password")]
    assert "shell history" in capsys.readouterr().err

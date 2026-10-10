from unittest.mock import MagicMock

from assistant import admin
from assistant.services import state


def test_add_owner(monkeypatch) -> None:
    upsert = MagicMock()
    monkeypatch.setattr(state, "upsert_user", upsert)
    admin.main(["add-owner", "42", "Ana"])
    upsert.assert_called_once_with("42", "Ana", role="owner")


def test_bot_profile_adds_the_owner_menu(monkeypatch) -> None:
    monkeypatch.setattr(state, "owner_chat_id", lambda: "42")
    tg = MagicMock()
    admin.bot_profile(tg, photo=False)
    assert tg.set_profile.call_count == 5
    chat_id, commands = tg.set_chat_commands.call_args.args
    names = [c["command"] for c in commands]
    assert chat_id == "42" and names[: len(admin.COMMANDS)] == list(admin.COMMANDS)
    assert names[len(admin.COMMANDS) :] == ["usuarios", "invitar", "catalogo"]
    tg.set_photo.assert_not_called()

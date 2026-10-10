import json

import httpx
import respx

from assistant.channels.telegram import API_BASE, Telegram, parse_update


@respx.mock
def test_send_message_with_keyboard() -> None:
    route = respx.post(f"{API_BASE}/bot1:x/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    Telegram("1:x").send_message("42", "hola", [[("Sí", "ok:1")]])
    body = route.calls.last.request.read()
    assert b'"callback_data":"ok:1"' in body


@respx.mock
def test_answer_callback() -> None:
    route = respx.post(f"{API_BASE}/bot1:x/answerCallbackQuery").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    Telegram("1:x").answer_callback("cb", "✓")
    assert route.called


@respx.mock
def test_send_animation() -> None:
    route = respx.post(f"{API_BASE}/bot1:x/sendAnimation").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    Telegram("1:x").send_animation("42", "https://x/g.gif")
    assert route.calls.last.request.read() == (
        b'{"chat_id":"42","animation":"https://x/g.gif"}'
    )


@respx.mock
def test_send_photo() -> None:
    route = respx.post(f"{API_BASE}/bot1:x/sendPhoto").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    Telegram("1:x").send_photo("42", "https://x/p.jpg")
    assert (
        route.calls.last.request.read() == b'{"chat_id":"42","photo":"https://x/p.jpg"}'
    )


@respx.mock
def test_url_button() -> None:
    route = respx.post(f"{API_BASE}/bot1:x/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    Telegram("1:x").send_message("42", "hola", [[("Guía", "https://g/")]])
    keyboard = json.loads(route.calls.last.request.read())["reply_markup"]
    assert keyboard == {"inline_keyboard": [[{"text": "Guía", "url": "https://g/"}]]}


@respx.mock
def test_webapp_send_pin_and_menu() -> None:
    sent = respx.post(f"{API_BASE}/bot1:x/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})
    )
    pin = respx.post(f"{API_BASE}/bot1:x/pinChatMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    menu = respx.post(f"{API_BASE}/bot1:x/setChatMenuButton").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    tg = Telegram("1:x")
    tg.pin("42", tg.send_webapp("42", "aquí", "Visor", "https://a/visor"))
    tg.clear_menu("42")
    app = {"text": "Visor", "web_app": {"url": "https://a/visor"}}
    assert json.loads(sent.calls.last.request.read())["reply_markup"] == {
        "inline_keyboard": [[app]]
    }
    assert json.loads(pin.calls.last.request.read()) == {
        "chat_id": "42",
        "message_id": 7,
        "disable_notification": True,
    }
    assert json.loads(menu.calls.last.request.read())["menu_button"] == {
        "type": "default"
    }


def test_service_messages_ignored() -> None:
    # The bot's own pinChatMessage comes back as an update without text.
    pinned = {"message_id": 7, "chat": {"id": 42}, "text": "tablero"}
    update = {
        "update_id": 1,
        "message": {"chat": {"id": 42}, "pinned_message": pinned},
    }
    assert parse_update(update) is None
    update["message"] = {"chat": {"id": 42}, "new_chat_members": [{"id": 1}]}
    assert parse_update(update) is None


def test_parse_caption_and_ignore_a_gif() -> None:
    gif = {"update_id": 1, "message": {"chat": {"id": 42}, "caption": "gasto"}}
    gif["message"]["animation"] = {"file_id": "g1"}
    msg = parse_update(gif)
    assert msg and (msg.text, msg.caption, msg.photo_file_id) == ("", "gasto", None)


def test_lang_from_language_code() -> None:
    from assistant.i18n import lang_of, t

    update = {
        "update_id": 1,
        "message": {"chat": {"id": 1}, "from": {"language_code": "zh-hant"}},
    }
    msg = parse_update(update)
    assert msg is not None and msg.language_code == "zh-hant"
    codes = ("zh-hant", "en-GB", "es-CO", "fr-CA", "de", "pt-br", None)
    assert [lang_of(c) for c in codes] == ["zh", "en", "es", "fr", "de", "en", "en"]
    assert t("fr", "viewer") == "Visionneuse de dépenses"
    assert t("pt", "viewer") == "Expense viewer"  # unknown: English


def test_every_text_in_every_language_with_the_same_placeholders() -> None:
    import string

    from assistant.i18n import CATEGORY_NAMES, LANGS, TEXTS

    def fields(text: str) -> set[str]:
        return {f for _, f, _, _ in string.Formatter().parse(text) if f}

    for key, texts in TEXTS.items():
        assert set(texts) == set(LANGS), key
        assert all(fields(texts[lang]) == fields(texts["en"]) for lang in LANGS), key
    assert all(set(names) == set(LANGS) for names in CATEGORY_NAMES.values())


@respx.mock
def test_bot_profile_in_every_language(monkeypatch) -> None:
    from assistant.admin import AVATAR, COMMANDS, bot_profile
    from assistant.services import state

    monkeypatch.setattr(state, "owner_chat_id", lambda: "42")

    routes = {
        m: respx.post(f"{API_BASE}/bot1:x/{m}").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        for m in (
            "setMyCommands",
            "setMyDescription",
            "setMyShortDescription",
            "setMyProfilePhoto",
        )
    }
    bot_profile(Telegram("1:x"), photo=True)
    bodies = [json.loads(c.request.read()) for c in routes["setMyCommands"].calls]
    owner = bodies.pop()
    assert owner["scope"] == {"type": "chat", "chat_id": "42"}
    assert "language_code" not in owner and len(owner["commands"]) == len(COMMANDS) + 3
    assert [b["language_code"] for b in bodies] == ["es", "", "zh", "fr", "de"]
    assert [c["command"] for c in bodies[1]["commands"]] == list(COMMANDS)
    for b in bodies:
        for c in b["commands"]:
            assert 1 <= len(c["description"]) <= 256
    for call in routes["setMyDescription"].calls:
        assert len(json.loads(call.request.read())["description"]) <= 512
    for call in routes["setMyShortDescription"].calls:
        assert len(json.loads(call.request.read())["short_description"]) <= 120
    upload = routes["setMyProfilePhoto"].calls.last.request.read()
    assert b'"attach://foto"' in upload and AVATAR.read_bytes() in upload


def test_parse_edited_message() -> None:
    update = {
        "update_id": 3,
        "edited_message": {"message_id": 7, "chat": {"id": 42}, "text": "-15 almuerzo"},
    }
    msg = parse_update(update)
    assert msg is not None and msg.edited and msg.text == "-15 almuerzo"
    assert not parse_update(
        {"update_id": 4, "message": update["edited_message"]}
    ).edited

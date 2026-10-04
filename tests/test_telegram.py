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
    Telegram("1:x").send_animation("42", "gif1")
    assert route.calls.last.request.read() == b'{"chat_id":"42","animation":"gif1"}'


@respx.mock
def test_pin_webapp() -> None:
    sent = respx.post(f"{API_BASE}/bot1:x/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})
    )
    pin = respx.post(f"{API_BASE}/bot1:x/pinChatMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    menu = respx.post(f"{API_BASE}/bot1:x/setChatMenuButton").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    Telegram("1:x").pin_webapp("42", "aquí", "Visor", "https://a/visor")
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
        "type": "web_app",
        **app,
    }


def test_parse_animation_caption_and_reply() -> None:
    gif = {"update_id": 1, "message": {"chat": {"id": 42}, "caption": "gasto"}}
    gif["message"]["animation"] = {"file_id": "g1"}
    msg = parse_update(gif)
    assert msg and (msg.text, msg.caption, msg.animation_file_id) == ("", "gasto", "g1")
    reply = {
        "update_id": 2,
        "message": {
            "chat": {"id": 42},
            "text": "/gif ingreso",
            "reply_to_message": {"animation": {"file_id": "g2"}},
        },
    }
    msg = parse_update(reply)
    assert msg and msg.reply_animation_file_id == "g2" and msg.animation_file_id is None
    assert (
        parse_update({"update_id": 3, "message": {"chat": {"id": 1}, "animation": 5}})
        is None
    )


def test_idioma_from_language_code() -> None:
    from assistant.i18n import idioma, t

    update = {
        "update_id": 1,
        "message": {"chat": {"id": 1}, "from": {"language_code": "zh-hant"}},
    }
    msg = parse_update(update)
    assert msg is not None and msg.language_code == "zh-hant"
    codes = ("zh-hant", "en-GB", "es-CO", "pt-br", None)
    assert [idioma(c) for c in codes] == ["zh", "en", "es", "es", "es"]
    assert t("fr", "visor") == "Visor de gastos"  # unknown: Spanish


@respx.mock
def test_bot_profile_in_three_languages() -> None:
    from assistant.admin import AVATAR, COMANDOS, bot_profile

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
    assert [b["language_code"] for b in bodies] == ["", "en", "zh"]
    assert [c["command"] for c in bodies[1]["commands"]] == list(COMANDOS)
    for b in bodies:
        for c in b["commands"]:
            assert 1 <= len(c["description"]) <= 256
    for call in routes["setMyDescription"].calls:
        assert len(json.loads(call.request.read())["description"]) <= 512
    for call in routes["setMyShortDescription"].calls:
        assert len(json.loads(call.request.read())["short_description"]) <= 120
    upload = routes["setMyProfilePhoto"].calls.last.request.read()
    assert b'"attach://foto"' in upload and AVATAR.read_bytes() in upload

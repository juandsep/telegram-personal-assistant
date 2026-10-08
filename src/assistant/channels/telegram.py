"""Telegram Bot API adapter.

Thin wrapper over the Bot API (HTTP, via httpx). sendMessage with optional
inline keyboard. The bot token is never logged.
"""

from __future__ import annotations

import httpx

from assistant.channels.base import Channel, InboundMessage

API_BASE = "https://api.telegram.org"
# Service updates (e.g. the bot's own pin) arrive as messages without text.
SERVICE = ("pinned_message", "new_chat_members", "left_chat_member", "new_chat_title")


def parse_update(update: object) -> InboundMessage | None:
    """A ``message`` (text or GIF) or ``callback_query``; None for anything else,
    service messages included."""
    if not isinstance(update, dict):
        return None
    try:
        if "callback_query" in update:
            cq = update["callback_query"]
            return InboundMessage(
                chat_id=str(cq["message"]["chat"]["id"]),
                text="",
                update_id=int(update["update_id"]),
                message_id=cq["message"].get("message_id"),
                callback_data=str(cq.get("data", "")),
                callback_query_id=str(cq["id"]),
                language_code=(cq.get("from") or {}).get("language_code"),
            )
        msg = update["message"]
        if any(k in msg for k in SERVICE):
            return None
        replied = (msg.get("reply_to_message") or {}).get("animation") or {}
        return InboundMessage(
            chat_id=str(msg["chat"]["id"]),
            text=str(msg.get("text", "")),
            update_id=int(update["update_id"]),
            message_id=msg.get("message_id"),
            animation_file_id=(msg.get("animation") or {}).get("file_id"),
            caption=str(msg.get("caption", "")),
            reply_animation_file_id=replied.get("file_id"),
            language_code=(msg.get("from") or {}).get("language_code"),
            photo_file_id=(msg.get("photo") or [{}])[-1].get("file_id"),
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


class Telegram(Channel):
    def __init__(self, bot_token: str, timeout: float = 10.0) -> None:
        self._token = bot_token
        self._client = httpx.Client(timeout=timeout)

    def _post(self, method: str, **payload: object) -> dict:
        resp = self._client.post(f"{API_BASE}/bot{self._token}/{method}", json=payload)
        resp.raise_for_status()
        return resp.json()

    def send_message(
        self,
        chat_id: str,
        text: str,
        inline_keyboard: list[list[tuple[str, str]]] | None = None,
    ) -> None:
        payload: dict[str, object] = {"chat_id": chat_id, "text": text}
        if inline_keyboard:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [
                        {"text": label, "url": data}  # a link button
                        if data.startswith("https://")
                        else {"text": label, "callback_data": data}
                        for label, data in row
                    ]
                    for row in inline_keyboard
                ]
            }
        self._post("sendMessage", **payload)

    def answer_callback(self, callback_query_id: str, text: str) -> None:
        self._post(
            "answerCallbackQuery",
            callback_query_id=callback_query_id,
            text=text,
        )

    def username(self) -> str:
        return str(self._post("getMe")["result"]["username"])

    def delete_message(self, chat_id: str, message_id: int) -> None:
        self._post("deleteMessage", chat_id=chat_id, message_id=message_id)

    def delete_messages(self, chat_id: str, message_ids: list[int]) -> None:
        """Up to 100 ids; Telegram skips the ones it cannot find."""
        self._post("deleteMessages", chat_id=chat_id, message_ids=message_ids)

    def download(self, file_id: str) -> bytes:
        """A file the user sent. Its URL carries the bot token: never log it."""
        path = self._post("getFile", file_id=file_id)["result"]["file_path"]
        resp = self._client.get(f"{API_BASE}/file/bot{self._token}/{path}")
        resp.raise_for_status()
        return resp.content

    def send_animation(self, chat_id: str, file_id: str) -> None:
        self._post("sendAnimation", chat_id=chat_id, animation=file_id)

    def set_profile(self, language_code: str, **texts: object) -> None:
        """Commands, description and short description for one language
        ("" = every language without its own)."""
        self._post(
            "setMyCommands", commands=texts["commands"], language_code=language_code
        )
        self._post(
            "setMyDescription",
            description=texts["description"],
            language_code=language_code,
        )
        self._post(
            "setMyShortDescription",
            short_description=texts["short_description"],
            language_code=language_code,
        )

    def set_photo(self, jpg: bytes) -> None:
        resp = self._client.post(
            f"{API_BASE}/bot{self._token}/setMyProfilePhoto",
            data={"photo": '{"type": "static", "photo": "attach://foto"}'},
            files={"foto": ("foto.jpg", jpg, "image/jpeg")},
        )
        resp.raise_for_status()

    def send_webapp(self, chat_id: str, text: str, label: str, url: str) -> int:
        """A message with a Mini App button; its message_id. Telegram signs the
        user into the app (no token in url)."""
        app = {"text": label, "web_app": {"url": url}}
        sent = self._post(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            reply_markup={"inline_keyboard": [[app]]},
        )
        return int(sent["result"]["message_id"])

    def pin(self, chat_id: str, message_id: int) -> None:
        self._post(
            "pinChatMessage",
            chat_id=chat_id,
            message_id=message_id,
            disable_notification=True,
        )

    def clear_menu(self, chat_id: str) -> None:
        """The chat's menu button back to Telegram's default (the commands)."""
        self._post(
            "setChatMenuButton", chat_id=chat_id, menu_button={"type": "default"}
        )

    def unpin_all(self, chat_id: str) -> None:
        self._post("unpinAllChatMessages", chat_id=chat_id)

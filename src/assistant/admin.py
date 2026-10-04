"""Admin CLI.

``python -m assistant.admin add-owner <chat_id> <nombre>``
``python -m assistant.admin migrate-gifs <owner_chat_id>``: copies the owner's
old per-user ``gifs/{chat_id}`` lists into the shared catalog's ``general``.
``python -m assistant.admin bot-profile [--photo docs/assets/juani-avatar.jpg]``:
the bot's commands, description and about text in es (default), en and zh, and
optionally its profile photo. Needs TELEGRAM_BOT_TOKEN.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from assistant.channels.telegram import Telegram
from assistant.i18n import IDIOMAS, t
from assistant.services import state

# The menu users see; owner commands (/invitar, /usuarios, /gif) stay unlisted.
COMANDOS = (
    "tablero",
    "ultimos",
    "editar",
    "anular",
    "calendario",
    "fun",
    "zona",
    "vincular",
    "conectar",
    "ayuda",
)


def bot_profile(telegram: Telegram, photo: Path | None) -> None:
    for lang in IDIOMAS:
        telegram.set_profile(
            "" if lang == "es" else lang,  # Spanish for every other language
            commands=[
                {"command": c, "description": t(lang, f"cmd_{c}")} for c in COMANDOS
            ],
            description=t(lang, "bot_description"),
            short_description=t(lang, "bot_about"),
        )
    if photo:
        telegram.set_photo(photo.read_bytes())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m assistant.admin")
    commands = parser.add_subparsers(dest="command", required=True)
    add_owner = commands.add_parser("add-owner", help="create or promote the owner")
    add_owner.add_argument("chat_id")
    add_owner.add_argument("nombre")
    migrate = commands.add_parser(
        "migrate-gifs", help="copy the owner's GIFs into the shared catalog"
    )
    migrate.add_argument("chat_id")
    profile = commands.add_parser(
        "bot-profile", help="set the bot's commands, texts and photo"
    )
    profile.add_argument("--photo", type=Path)
    args = parser.parse_args(argv)
    if args.command == "bot-profile":
        bot_profile(Telegram(os.environ["TELEGRAM_BOT_TOKEN"]), args.photo)
        print("bot profile updated")
        return
    if args.command == "migrate-gifs":
        print(f"{state.migrate_gifs(args.chat_id)} gifs migrated")
        return
    state.upsert_user(args.chat_id, args.nombre, rol="owner")
    print("owner saved")


if __name__ == "__main__":
    main()

"""Admin CLI.

``python -m assistant.admin add-owner <chat_id> <name>``
``python -m assistant.admin anonymize-exports``: one-off, rewrites the ledger
CSVs written before the alias in ``<GCP_PROJECT_ID>-backup`` with your own
credentials (the worker may only create objects).
``python -m assistant.admin bot-profile [--photo]``:
the bot's commands, description and about text in every language, the owner's
own menu with the owner commands added (the owner is read from Firestore, so
GCP_PROJECT_ID, plus FIRESTORE_DATABASE for staging), and optionally its
profile photo (``AVATAR``). Needs TELEGRAM_BOT_TOKEN.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from assistant.channels.telegram import Telegram
from assistant.i18n import LANGS, t
from assistant.services import state

AVATAR = Path(__file__).resolve().parents[2] / "docs" / "assets" / "juani-avatar.jpg"
# The menu users see; the manual /zona override stays unlisted. The owner's own
# menu adds OWNER_COMMANDS (answered in Spanish only).
COMMANDS = (
    "tablero",
    "resumen",
    "ultimos",
    "anular",
    "calendario",
    "fun",
    "moneda",
    "reset",
    "ayuda",
)
OWNER_COMMANDS = {
    "usuarios": "Quién tiene acceso y quién lo usa",
    "invitar": "Invitar a alguien: /invitar <nombre>",
    "catalogo": "Imágenes de reacciones",
}


def bot_profile(telegram: Telegram, photo: bool) -> None:
    for lang in LANGS:
        telegram.set_profile(
            "" if lang == "en" else lang,  # English for every other language
            commands=[
                {"command": c, "description": t(lang, f"cmd_{c}")} for c in COMMANDS
            ],
            description=t(lang, "bot_description"),
            short_description=t(lang, "bot_about"),
        )
    if owner := state.owner_chat_id():
        commands = [
            {"command": c, "description": t("es", f"cmd_{c}")} for c in COMMANDS
        ]
        commands += [
            {"command": c, "description": d} for c, d in OWNER_COMMANDS.items()
        ]
        telegram.set_chat_commands(owner, commands)
    if photo:
        telegram.set_photo(AVATAR.read_bytes())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m assistant.admin")
    commands = parser.add_subparsers(dest="command", required=True)
    add_owner = commands.add_parser("add-owner", help="create or promote the owner")
    add_owner.add_argument("chat_id")
    add_owner.add_argument("name")
    profile = commands.add_parser(
        "bot-profile", help="set the bot's commands, texts and photo"
    )
    profile.add_argument("--photo", action="store_true", help="also set AVATAR")
    commands.add_parser("anonymize-exports", help="alias and no note in old CSVs")
    args = parser.parse_args(argv)
    if args.command == "anonymize-exports":
        from google.cloud import storage

        from assistant.jobs import backup

        project = os.environ["GCP_PROJECT_ID"]
        bucket = storage.Client(project=project).bucket(f"{project}-backup")
        print(f"{backup.anonymize_exports(bucket)} files rewritten")
        return
    if args.command == "bot-profile":
        bot_profile(Telegram(os.environ["TELEGRAM_BOT_TOKEN"]), args.photo)
        print("bot profile updated")  # the owner's menu too, if there is one
        return
    state.upsert_user(args.chat_id, args.name, role="owner")
    print("owner saved")


if __name__ == "__main__":
    main()

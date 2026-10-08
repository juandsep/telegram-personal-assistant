"""Reaction catalog: images and GIFs by tag, sent after a registration or a
meal photo when /fun is on.

The owner fills it from the ``/catalogo`` Mini App (``api.py``), not from the
chat. Files live in the public-read ``MEDIA_BUCKET`` under ``media/`` (the
bucket grants object reads, never listing) and Telegram fetches them by URL.
Tags are ``<kind>/<key>``: ``gasto/<categoria>``, ``ingreso/<fuente>``,
``comida/sana|meh|chatarra``; ``<kind>/general`` is the fallback of a kind.

- ``media/{id}`` (Firestore): etiqueta, url, tipo (foto|gif), objeto (the
  bucket path), creado.

Every file is checked by its magic bytes: only JPEG, PNG, WebP and GIF, at
most 5 MB (Telegram's limit for a photo sent by URL).
"""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from functools import cache
from typing import Any

import google.cloud.storage as storage
from google.cloud import firestore
from google.cloud.firestore import FieldFilter

from assistant.config import get_worker_settings
from assistant.services import state

log = logging.getLogger(__name__)

KINDS = ("gasto", "ingreso", "comida")
GENERAL = "general"
SUGGESTED = (
    "gasto/general",
    "ingreso/general",
    "comida/sana",
    "comida/meh",
    "comida/chatarra",
)
MAX_BYTES = 5 * 1024 * 1024
_TAG = re.compile(rf"({'|'.join(KINDS)})/(\w{{1,24}})")


class MediaRejected(ValueError):
    """Not an allowed image, too big, or a bad tag."""


def valid_tag(tag: str) -> bool:
    return bool(_TAG.fullmatch(tag)) and tag == tag.lower()


def sniff(data: bytes) -> tuple[str, str] | None:
    """(content type, extension) from the magic bytes; None if not allowed."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


@cache
def _bucket() -> Any:
    s = get_worker_settings()
    return storage.Client(project=s.project_id).bucket(s.media_bucket)


def _col() -> Any:
    return state._db().collection("media")


def add(tag: str, data: bytes) -> str:
    """Store one file under ``tag``; its id."""
    kind = sniff(data)
    if not valid_tag(tag) or kind is None or len(data) > MAX_BYTES:
        raise MediaRejected("rejected")
    media_id = uuid.uuid4().hex
    name = f"media/{media_id}.{kind[1]}"
    blob = _bucket().blob(name)
    blob.cache_control = "public, max-age=31536000, immutable"
    blob.upload_from_string(data, content_type=kind[0])
    _col().document(media_id).set(
        {
            "etiqueta": tag,
            "url": f"https://storage.googleapis.com/{_bucket().name}/{name}",
            "tipo": "gif" if kind[0] == "image/gif" else "foto",
            "objeto": name,
            "creado": firestore.SERVER_TIMESTAMP,
        }
    )
    log.info("media_added")
    return media_id


def remove(media_id: str) -> bool:
    """Drop one file and its doc; False if unknown."""
    if not re.fullmatch(r"[0-9a-f]{32}", media_id):
        return False
    ref = _col().document(media_id)
    snap = ref.get()
    if not snap.exists:
        return False
    try:
        _bucket().blob(snap.to_dict()["objeto"]).delete()
    except Exception as exc:  # the doc goes anyway; an orphan file is harmless
        log.warning("media_delete_failed error=%s", type(exc).__name__)
    ref.delete()
    log.info("media_removed")
    return True


def catalog() -> list[dict]:
    """Every item as {id, etiqueta, url, tipo}, by tag then newest last."""
    # ponytail: reads the whole collection; fine for an owner-curated few hundred.
    items = [{**(s.to_dict() or {}), "id": s.id} for s in _col().stream()]
    return sorted(items, key=lambda d: (d["etiqueta"], str(d.get("creado", ""))))


def pick(kind: str, key: str) -> tuple[str, str] | None:
    """(url, tipo) of a random item of ``kind/key``, else of ``kind/general``."""
    for tag in (f"{kind}/{key}", f"{kind}/{GENERAL}"):
        query = _col().where(filter=FieldFilter("etiqueta", "==", tag))
        items = [s.to_dict() or {} for s in query.stream()]
        if items:
            item = secrets.choice(items)
            return str(item["url"]), str(item["tipo"])
    return None

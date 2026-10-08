from unittest.mock import MagicMock

import pytest
from firestore_fake import FakeDB

from assistant.services import media, state

JPG = b"\xff\xd8\xff\xe0" + b"x" * 10
GIF = b"GIF89a" + b"x" * 10


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    fake = FakeDB()
    monkeypatch.setattr(state, "_db", lambda: fake)
    return fake


@pytest.fixture
def bucket(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    fake.name = "jd-botjonh-media"
    monkeypatch.setattr(media, "_bucket", lambda: fake)
    return fake


def test_sniff_by_magic_bytes() -> None:
    assert media.sniff(JPG) == ("image/jpeg", "jpg")
    assert media.sniff(b"\x89PNG\r\n\x1a\n...") == ("image/png", "png")
    assert media.sniff(GIF) == ("image/gif", "gif")
    assert media.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ("image/webp", "webp")
    assert media.sniff(b"<svg onload=alert(1)>") is None
    assert media.sniff(b"") is None


def test_valid_tag() -> None:
    assert media.valid_tag("gasto/restaurantes") and media.valid_tag("comida/sana")
    assert media.valid_tag("ingreso/año_2")
    for bad in ("gasto", "otro/x", "gasto/a b", "Gasto/x", "gasto/" + "x" * 25):
        assert not media.valid_tag(bad)


def test_add_uploads_public_file_and_indexes_it(db: FakeDB, bucket: MagicMock) -> None:
    media_id = media.add("gasto/restaurantes", JPG)
    name = f"media/{media_id}.jpg"
    bucket.blob.assert_called_with(name)
    bucket.blob().upload_from_string.assert_called_once_with(
        JPG, content_type="image/jpeg"
    )
    doc = db.store[f"media/{media_id}"]
    assert doc["url"] == f"https://storage.googleapis.com/jd-botjonh-media/{name}"
    assert (doc["etiqueta"], doc["tipo"], doc["objeto"]) == (
        "gasto/restaurantes",
        "foto",
        name,
    )
    assert db.store[f"media/{media.add('comida/sana', GIF)}"]["tipo"] == "gif"


@pytest.mark.parametrize(
    ("tag", "data"),
    [
        ("gasto/x", b"<html>"),
        ("nope", JPG),
        ("gasto/x", JPG + b"x" * media.MAX_BYTES),
    ],
)
def test_add_rejects_bad_files_and_tags(
    db: FakeDB, bucket: MagicMock, tag: str, data: bytes
) -> None:
    with pytest.raises(media.MediaRejected):
        media.add(tag, data)
    bucket.blob.assert_not_called()
    assert db.store == {}


def test_pick_falls_back_to_general_and_remove(db: FakeDB, bucket: MagicMock) -> None:
    assert media.pick("gasto", "salud") is None
    general = media.add("gasto/general", GIF)
    food = media.add("gasto/restaurantes", JPG)
    assert media.pick("gasto", "restaurantes")[1] == "foto"
    assert media.pick("gasto", "salud")[1] == "gif"
    assert media.pick("gasto", "")[1] == "gif"
    assert [d["id"] for d in media.catalog()] == [general, food]
    bucket.blob().delete.side_effect = RuntimeError("gone")
    assert media.remove(food) is True  # the doc goes even if the file fails
    assert media.remove(food) is False
    assert media.remove("../users/42") is False
    assert media.pick("gasto", "restaurantes")[1] == "gif"

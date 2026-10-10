import copy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from assistant.context import ToolContext
from assistant.i18n import t
from assistant.services import state


class Snap:
    def __init__(self, doc_id, data):
        self.id, self._data, self.exists = doc_id, data, data is not None

    def to_dict(self):
        return copy.deepcopy(self._data)


class Ref:
    def __init__(self, store, key):
        self.store, self.key = store, key

    def get(self, transaction=None):
        return Snap(self.key[1], self.store.get(self.key))

    def set(self, data, merge=False):
        base = self.store.get(self.key, {}) if merge else {}
        self.store[self.key] = {**base, **copy.deepcopy(data)}

    def update(self, data):
        self.store[self.key].update(data)

    def delete(self):
        self.store.pop(self.key, None)


class Tx:
    """Just enough of firestore.Transaction for @firestore.transactional."""

    _read_only, _max_attempts, _id = False, 1, None

    def _clean_up(self): ...
    def _begin(self, retry_id=None): ...
    def _commit(self): ...
    def _rollback(self): ...

    def set(self, ref, data, merge=False):
        ref.set(data, merge)

    def update(self, ref, data):
        ref.update(data)

    def delete(self, ref):
        ref.delete()


class Collection:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def document(self, doc_id):
        return Ref(self.store, (self.name, doc_id))

    def stream(self):
        return [Snap(k[1], v) for k, v in self.store.items() if k[0] == self.name]


class FakeDB:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return Collection(self.store, name)

    def transaction(self):
        return Tx()

    def recursive_delete(self, ref):  # the doc; subcollections live as name/id/...
        name, doc_id = ref.key
        for key in [k for k in self.store if k[0] == name]:
            if key[1] == doc_id or key[1].startswith(f"{doc_id}/"):
                del self.store[key]


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(state, "_db", lambda: fake)
    return fake


def ctx(role="owner"):
    return ToolContext("1", role, "USD", "America/Panama", 1, datetime.now(UTC))


def test_users(db) -> None:
    assert state.get_user("1") is None
    state.upsert_user("1", "Ana", role="owner")
    state.set_last_batch("1", "b1")
    state.upsert_user("1", "Ana", role="owner", currency="PAB")
    assert state.get_user("1")["moneda"] == "PAB"
    assert state.last_batch("1") == "b1"
    assert state.last_batch("2") is None
    assert state.list_chat_ids() == ["1"]


def test_set_currency_guesses_the_zone_once(db) -> None:
    state.set_currency("1", "COP")  # no zone yet
    assert state.get_user("1") == {"moneda": "COP", "zona_horaria": "America/Bogota"}
    state.set_currency("1", "EUR")  # a zone set by now is kept
    assert state.get_user("1") == {"moneda": "EUR", "zona_horaria": "America/Bogota"}
    state.set_timezone("2", "America/Panama")  # the old default is replaced
    state.set_currency("2", "CNY")
    assert state.get_user("2")["zona_horaria"] == "Asia/Shanghai"


def test_mark_processed_once(db) -> None:
    assert state.mark_processed(7) is True
    assert state.mark_processed(7) is False
    assert db.store[("processed", "7")]["expire_at"] > datetime.now(UTC)
    state.unmark_processed(7)
    assert state.mark_processed(7) is True


def test_invite_single_use(db) -> None:
    out = state.invite_beta(ctx(), "Beto")
    code = out.split("/start ")[1].split(" ")[0]
    assert state.redeem_invite(code, "2") is True
    assert state.get_user("2")["rol"] == "beta"
    assert state.get_user("2")["nombre"] == "Beto"
    assert "zona_horaria" not in state.get_user("2")  # readers fall back
    assert state.redeem_invite(code, "3") is False
    assert state.get_user("3") is None


def test_invite_expired_or_bogus(db) -> None:
    code = "a" * 22
    db.store[("invites", code)] = {
        "nombre": "x",
        "used": False,
        "expire_at": datetime.now(UTC) - timedelta(seconds=1),
    }
    assert state.redeem_invite(code, "2") is False
    assert state.redeem_invite("../users/1", "2") is False
    assert state.redeem_invite("b" * 22, "2") is False


def test_owner_only_tools(db) -> None:
    assert state.invite_beta(ctx("beta"), "x") == state.OWNER_ONLY
    assert state.list_users(ctx("beta")) == state.OWNER_ONLY
    assert not db.store
    state.upsert_user("1", "Ana", role="owner")
    assert state.list_users(ctx()) == "Ana (owner)"


def test_rate_limit(db) -> None:
    assert [state.check_rate("1", 2) for _ in range(3)] == [True, True, False]
    assert state.check_rate("2", 2) is True


def test_spend_as_string(db) -> None:
    assert state.llm_spend_today("1") == Decimal("0")
    state.add_llm_spend("1", Decimal("0.01"))
    state.add_llm_spend("1", Decimal("0.02"))
    assert state.llm_spend_today("1") == Decimal("0.03")
    (doc,) = [v for k, v in db.store.items() if k[0] == "spend"]
    assert doc["usd"] == "0.03"


def test_preferences(db) -> None:
    assert state.get_preferences("1") == {}
    db.store[("preferences", "1")] = {"presupuesto": {"salud": "10"}}
    assert state.get_preferences("1")["presupuesto"] == {"salud": "10"}


def test_pending(db) -> None:
    token = state.create_pending("1", {"tool": "undo"})
    assert state.pop_pending("2", token) is None  # other chat
    assert state.pop_pending("1", token) == {"tool": "undo"}
    assert state.pop_pending("1", token) is None  # single use
    assert state.pop_pending("1", "bad/token") is None


def test_pending_expired(db) -> None:
    token = state.create_pending("1", {"tool": "x"})
    db.store[("pending", token)]["expire_at"] = datetime.now(UTC)
    assert state.pop_pending("1", token) is None
    assert ("pending", token) not in db.store


def test_oauth_state_single_use_and_expiry(db) -> None:
    token = state.create_oauth_state("1")
    assert db.store[("oauth_states", token)]["expire_at"] > datetime.now(UTC)
    assert state.consume_oauth_state(token) == "1"
    assert state.consume_oauth_state(token) is None  # single use
    old = state.create_oauth_state("1")
    db.store[("oauth_states", old)]["expire_at"] = datetime.now(UTC)
    assert state.consume_oauth_state(old) is None
    assert ("oauth_states", old) not in db.store
    assert state.consume_oauth_state("../users/1") is None


def test_history_keeps_last_turns(db) -> None:
    assert state.get_history("1") == []
    for i in range(8):
        state.append_history(
            "1",
            [{"role": "user", "content": str(i)}, {"role": "assistant", "content": ""}],
        )
    history = state.get_history("1")
    assert len(history) == 12
    assert history[0]["content"] == "2"


def test_ics_token_created_reused_and_rotated(db) -> None:
    assert state.chat_for_ics_token("x" * 32) is None
    token = state.ics_token("1")
    assert len(token) == 32 and state.ics_token("1") == token
    assert state.chat_for_ics_token(token) == "1"
    new = state.ics_token("1", rotate=True)
    assert new != token
    assert state.chat_for_ics_token(token) is None  # old link revoked
    assert state.chat_for_ics_token(new) == "1"
    assert state.get_user("1")["ics_token"] == new


def test_ics_token_format_checked_before_lookup(monkeypatch) -> None:
    def boom():
        raise AssertionError("no Firestore lookup")

    monkeypatch.setattr(state, "_db", boom)
    for bad in ("", "short", "a" * 31 + "/", "../users/1" + "a" * 22, "a" * 33):
        assert state.chat_for_ics_token(bad) is None


def test_revoke_only_betas(db) -> None:
    db.store[("users", "1")] = {"nombre": "Yo", "rol": "owner"}
    db.store[("users", "2")] = {"nombre": "Ana", "rol": "beta"}
    assert state.revoke("1") is False
    assert state.revoke("3") is False
    assert state.revoke("2") is True
    assert state.get_user("2") is None and state.get_user("1") is not None


def test_reset_user_keeps_access_only(db) -> None:
    state.upsert_user("1", "Ana", role="beta", currency="COP")
    state.ics_token("1")
    token = state.get_user("1")["ics_token"]
    db.store[("ledger", "1/movimientos/a")] = {"monto": "5"}
    db.store[("agenda", "1/eventos/e")] = {"texto": "x"}
    db.store[("ledger", "2/movimientos/b")] = {"monto": "7"}  # another chat
    state.append_history("1", [{"role": "user", "content": "hola"}])
    db.store[("preferences", "1")] = {"gcal_id": "c"}
    state.reset_user("1")
    assert state.get_user("1") == {"nombre": "Ana", "rol": "beta"}
    assert state.chat_for_ics_token(token) is None
    assert state.get_history("1") == []
    assert state.get_preferences("1") == {}
    assert set(db.store) == {("users", "1"), ("ledger", "2/movimientos/b")}


def test_mark_seen(db) -> None:
    state.upsert_user("1", "Ana", role="beta")
    state.mark_seen("1", "2026-10-09")
    assert state.get_user("1")["ultimo_uso"] == "2026-10-09"


def test_access_request_one_a_day_and_reject_wait(db) -> None:
    state.upsert_user("1", "Yo", role="owner")
    assert state.owner_chat_id() == "1"
    assert state.request_access("7", "Ana", "es") == "sent"
    assert state.request_access("7", "Ana", "es") == "pending"
    assert state.request_access("8", "Leo", "en") == "today"
    assert state.reject_request("7")["nombre"] == "Ana"
    assert state.reject_request("7") is None  # no longer pending
    assert state.request_access("7", "Ana", "es") == "wait"
    db.store.pop(("requests", f"day-{datetime.now(UTC).date()}"))
    assert state.request_access("8", "Leo", "en") == "sent"
    assert state.accept_request("8")["idioma"] == "en"
    assert state.get_user("8")["rol"] == "beta"
    assert ("requests", "8") not in db.store


def test_access_request_full(db, monkeypatch) -> None:
    monkeypatch.setattr(state, "MAX_USERS", 1)
    state.upsert_user("1", "Yo", role="owner")
    assert state.request_access("7", "Ana", "es") == "full"
    assert state.accept_request("7") is None


def test_revoke_schedules_the_purge(db) -> None:
    db.store[("users", "2")] = {"nombre": "Ana", "rol": "beta", "alias": "a2"}
    db.store[("ledger", "2")] = {}
    assert state.revoke("2") is True
    assert state.due_purges() == []  # 30 days to go
    db.store[("purge", "2")]["due"] = datetime.now(UTC) - timedelta(seconds=1)
    assert state.due_purges() == ["2"]
    state.purge_user("2")
    assert ("ledger", "2") not in db.store
    assert ("purge", "2") not in db.store and state.get_user("2") is None


def test_user_alias_is_created_once(db) -> None:
    state.upsert_user("2", "Ana", role="beta")
    alias = state.user_alias("2", state.get_user("2"))
    assert len(alias) == 12
    assert state.user_alias("2", state.get_user("2")) == alias


def test_calendar_status(db) -> None:
    state.upsert_user("1", "Ana", role="beta")
    assert state.calendar_status(ctx()) == t("es", "cal_status_none")
    token = state.ics_token("1")
    assert state.calendar_status(ctx()) == t("es", "cal_status_feed_wait")
    state.mark_ics_fetch(token)
    db.store[("preferences", "1")] = {"gcal_token_enc": "x"}
    assert state.calendar_status(ctx()) == "\n".join(
        [t("es", "cal_status_google"), t("es", "cal_status_feed_ok", minutes=0)]
    )

# Module contracts

Three branches build the worker in parallel. Each module imports the others
lazily (inside functions) and tests them with mocks, so each branch passes CI
on its own. Signatures here are the contract; change them only in this file.

All tool implementations: `fn(ctx: ToolContext, **args) -> str`. The string is
short data for the LLM to summarize, never PII in logs. Settings come from
`assistant.config.get_worker_settings()`; shared types from
`assistant.context`.

## services/state.py (Firestore)

```python
def get_user(chat_id: str) -> dict | None            # users/{chat_id}
def upsert_user(chat_id: str, name: str, role: str, currency: str = "USD",
                timezone: str = "America/Panama") -> None   # users.nombre/rol/moneda/zona_horaria
def mark_processed(update_id: int) -> bool           # True if new; transaction, 7-day TTL field
def unmark_processed(update_id: int) -> None         # api: undo when publish fails
def redeem_invite(code: str, chat_id: str) -> bool   # transaction: single use, 24 h, creates beta user
def check_rate(chat_id: str, limit_per_minute: int) -> bool   # True if allowed
def llm_spend_today(chat_id: str) -> Decimal
def add_llm_spend(chat_id: str, usd: Decimal) -> None
def get_preferences(chat_id: str) -> dict            # {"presupuesto": {category: str(Decimal)}, ...}
def create_pending(chat_id: str, action: dict) -> str   # token, expires in 10 min
def pop_pending(chat_id: str, token: str) -> dict | None
def get_history(chat_id: str) -> list[dict]          # last 6 turns, OpenAI message format
def append_history(chat_id: str, messages: list[dict]) -> None
def set_last_batch(chat_id: str, batch_id: str) -> None
def last_batch(chat_id: str) -> str | None
def list_chat_ids() -> list[str]                     # for cron jobs
def ics_token(chat_id: str, rotate: bool = False) -> str   # ics_tokens/{token}; rotate revokes
def chat_for_ics_token(token: str) -> str | None     # format checked before any lookup
# tools
def invite_beta(ctx, name: str) -> str               # owner only, checked in code
def list_users(ctx) -> str                           # owner only
```

## services/ledger.py, fx.py, budgets.py, agenda.py, busy.py, gcal.py

```python
# ledger: Firestore ledger/{chat_id}/movimientos, append-only (never edits or
# deletes), Decimal amounts as strings, idempotent by doc id ({update_id}-{i},
# {update_id}-i0, undo {batch_id}-r{i}, edit/void {registro_id}-x and
# {update_id}-e0). Every amount is USD: monto (USD), moneda="USD",
# monto_original, moneda_original, tasa (moneda_original per 1 USD), fuente_tasa
# (usd|trm|ecb); a reverso has reversa=<registro doc id>. Users write any
# currency; code converts with fx.to_usd at the movement's date. On FxError
# nothing is written and the reply is "No pude obtener la tasa de <CUR>, intenta
# luego." or "Moneda no soportada."; monto <= 0 -> "El monto debe ser mayor que 0."
# Replies are one line: "−0.49 USD · café (2,000 COP)", "+1000.00 USD · nota"
# (label = nota, else categoria/fuente; items joined with "; "). A blank gasto
# categoria is stored as "otros".
# items: [{amount, category, note?}] (stored as monto/categoria/nota)
def record_expense(ctx, items: list[dict], currency: str, day: date) -> str
def record_income(ctx, amount: Decimal, currency: str, source: str, day: date,
                  note: str | None = None) -> str
def finance_summary(ctx, period: str) -> str         # hoy|semana|mes, user's currency
def undo(ctx, batch_id: str | None = None) -> str    # appends reverso rows
def spend_by_category(chat_id: str, since: date, until: date, base: str = "USD") -> dict[str, Decimal]
def total_income(chat_id: str, since: date, until: date, base: str = "USD") -> Decimal
def query_entries(chat_id: str, field: str, since, until) -> list[dict]  # since <= field < until
# Editing: the last registros not cancelled by a reverso, newest (creado) first.
# latest item keys: index (1..n), id, then the stored fields fecha, tipo_mov,
# monto (USD), monto_original, moneda_original, categoria (gasto) | fuente
# (ingreso), nota.
def latest(ctx, n: int = 5) -> list[dict]
def latest_text(ctx, n: int = 5) -> str              # "1) 30/09 −0.49 USD café (2,000 COP)"
                                                     # one per line; "Sin movimientos."
# edit: reverso of entry <index> + new registro (batch e{update_id}) with
# the merged fields; amount/currency re-converted at the original fecha. A retry of
# the same update answers the same and writes nothing.
def edit(ctx, index: int = 1, amount: Decimal | None = None, currency: str | None = None,
         category: str | None = None, note: str | None = None) -> str
                                                     # "✓ editado: −1.00 USD · café"
def void(ctx, index: int = 1) -> str                 # reverso only: "✓ anulado: ..."
# Bad index -> "No encontré ese movimiento."
# fx: rates to USD in code, never the LLM. COP = official TRM (datos.gov.co
# 32sa-8pi3, latest row with vigenciadesde <= fecha, "trm"); ECB currencies via
# Frankfurter (base=USD, "ecb"); USD -> rate 1, "usd", no HTTP. httpx 5 s, no
# redirects. Cached in Firestore fx/{YYYY-MM-DD}_{CUR} = {tasa, fuente}.
class FxError(Exception): ...                        # str(e): unsupported|http|data|cache
def to_usd(amount: Decimal, currency: str, day: date) -> tuple[Decimal, Decimal, str]
                                                     # (usd 0.01, currency per USD, source)
# budgets: pure rules, no LLM
def recommend_budget(ctx, period: str = "mes") -> str
# agenda: Firestore agenda/{chat_id}/eventos/{event_id}, user's zone.
# event_id = {update_id} ({update_id}-{n} for another item of the same turn),
# create() so a retry answers the same; cancel sets estado=cancelado (never
# deletes). A reminder (recordatorio: at when; evento: start - reminder_min)
# within 30 days is a Cloud Task r-<sha256(chat_id:event_id)[:32]>; the digest
# enqueues later ones once they enter the 30-day horizon.
def create_event(ctx, title: str, start: datetime, end: datetime | None = None,
                 location: str | None = None, reminder_min: int | None = None) -> str
def list_agenda(ctx, period: str) -> str             # hoy|manana|semana
def agenda_lines(ctx, period: str) -> list[str]      # lines for the digest
def cancel_event(ctx, event_id: str) -> str
def create_reminder(ctx, text: str, when: datetime) -> str   # 15 min, reminder at when
def free_slots(ctx, day: date) -> str                # tool over free_slot_list()
def conflicts(ctx, start: datetime, end: datetime) -> list[str]  # "Dentista 09:00–10:00"
def free_slot_list(ctx, day: date) -> list[str]      # free slots 08:00–20:00, "11:00–19:00"
def week_text(ctx) -> str                            # /calendario, no LLM
def enqueue_reminders(ctx) -> None                   # digest: reminders now within 30 days
def reminder_text(chat_id: str, event_id: str) -> str | None   # "⏰ <titulo> <HH:MM>"; None if gone
def ics(chat_id: str, now: datetime) -> str          # VCALENDAR, -30 d to +365 d
# busy (separate branch): external ICS busy blocks. Loaded with importlib; when
# missing or raising, the agenda ignores it (logs the error class only).
def busy_blocks(chat_id: str, since: datetime, until: datetime) -> list[tuple[datetime, datetime, str]]
def connect(ctx, url: str) -> str                    # a lone secret iCal link
# gcal: mirror into the user's own Google Calendar. OAuth (scope
# calendar.events): the refresh token KMS-encrypted in
# preferences/{chat_id}.gcal_token_enc, calls on "primary" with a cached access
# token; 400 invalid_grant drops it. Legacy: preferences/{chat_id}.gcal_id, a
# calendar shared with the service account, called with ADC. Calendar REST v3
# over httpx, 5 s. Google event id =
# "bj" + sha256(chat_id:event_id)[:40] (base32hex-safe): insert 409 and delete
# 404/410 count as done. Mirror calls never raise (log codes only); agenda calls
# them after the Firestore write via importlib. busy_blocks reads events.list and
# skips our own "bj…" ids, so an event never conflicts with its mirror.
def auth_url(s: WorkerSettings, state_token: str) -> str  # Google consent page
def connect(chat_id: str, code: str, s: WorkerSettings) -> None  # code -> refresh token
def disconnect(chat_id: str) -> None                 # cal:off; revokes, clears all
def mirror_create(ctx, event_id: str, event: dict) -> None
def mirror_cancel(ctx, event_id: str) -> None
def busy_blocks(chat_id: str, since: datetime, until: datetime) -> list[tuple[datetime, datetime, str]]
```

Conflicts: `llm/tools.py` calls `agenda.conflicts` before `create_event` and
`create_reminder` (only `tipo=evento` items and busy blocks count). On a conflict
the call is stored as pending and the user gets "Choca con … ¿Agendo igual?"
with Confirmar/Cancelar; `execute_pending` runs it without checking again.

## jobs/__init__.py

```python
def run_job(name: str) -> None   # digest|checkin|weekly; digest exports yesterday's
                                 # ledger CSV, weekly backs up JSON to GCS
# CSV (BigQuery botjonh.ledger): fecha,chat_id,tipo_mov,categoria,monto,moneda,
# nota,batch_id,tipo,monto_original,moneda_original,tasa (monto in USD; older
# files lack the last three columns, read as NULL via allow_jagged_rows).
```

## llm/client.py, llm/tools.py

```python
class LLMUnavailable(Exception): ...   # 429/5xx/timeout: worker returns 5xx to Pub/Sub

@dataclass
class TurnResult:
    reply: str
    keyboard: list[list[tuple[str, str]]] | None   # confirmation buttons
    messages: list[dict]                           # new turns to append to history
    tools: list[str]
    prompt_version: str
    model: str
    tokens_hit: int
    tokens_miss: int
    tokens_out: int
    cost_usd: Decimal
    rejected: int                                  # tool calls rejected by validation

def run_turn(ctx: ToolContext, text: str, history: list[dict]) -> TurnResult
def execute_pending(ctx: ToolContext, token: str) -> str   # tools.py; after "ok:<token>" button
```

Confirmation buttons use `callback_data` `ok:<token>` and `no:<token>`.

## observability/trace.py

```python
def record_turn(result: TurnResult, latency_ms: int, text: str) -> None
```

Emits one structured JSON log line, `{"event": "llm_turn", ...}` (no PII;
`text` only as sha256). The log-based metrics in `infra/monitoring.tf` parse its
fields, so keep the `"field": value` format (asserted in
`tests/test_trace.py`). Never raises.

## Worker routes without the LLM

- `/calendario` (next 7 days plus a button: `cal:menu`, or `cal:off` when a
  calendar is connected), `/calendario off`, `/calendario nuevo` (rotate the
  ICS token). Buttons: `cal:menu` → `cal:g` (a link to `/oauth/google?s=<state>`,
  `state.create_oauth_state`) | `cal:i` (a link to `/ics/{token}/suscribir`),
  `cal:off` (`gcal.disconnect`). A lone secret iCal link runs `busy.connect`
  and deletes the message.
- `POST /tasks/reminder` `{"chat_id", "evento_id"}` from Cloud Tasks: sends
  `agenda.reminder_text`; always 2xx except a Firestore failure.
- api `GET /ics/{token}.ics`: public, 404 for a bad or unknown token.
  `GET /ics/{token}/suscribir`: 302 to `webcal://<host>/ics/{token}.ics`.
- api `GET /oauth/google?s=<state>`: 302 to Google's consent page.
  `GET /oauth/google/callback?code&state`: consumes the single-use state,
  `gcal.connect`, backfills, tells the chat in Telegram; a small HTML page.

## Worker order per update

1. Rate limit and daily cap (no LLM call when exceeded).
2. `run_turn`; `LLMUnavailable` -> 503.
3. Send the reply via Telegram.
4. `add_llm_spend`, `append_history`.
5. `record_turn`.
6. Return 2xx.

# Using Juani

Everything a user can do with Juani, in detail. Back to the
[README](../README.md).

## Languages

Juani speaks Spanish, English and Chinese. The language comes from the
`language_code` of the user's Telegram app (it follows the phone unless changed
in Telegram) and is saved as `users.idioma` whenever it changes, so the
scheduled messages use it too. Anything other than English or Chinese falls back
to Spanish.

`src/assistant/i18n.py` holds every reply, the reports, the dashboard and the
category names (stored keys stay Spanish, so no data changes with the
language). The LLM is told to answer in the user's language. Commands keep their
Spanish names (`/tablero`, `/ultimos`…) in every language. Only the owner-only
commands (`/invitar`, `/usuarios`, `/gif`) answer in Spanish.

## Getting started

Only invited people can use the bot. The owner sends `/invitar <name>` and
forwards the single-use `t.me` link (valid 24 h). Opening it sends `/start`,
which creates the user, shows Juani's welcome and pins the Visor de gastos
(see [Dashboard](#dashboard-visor-de-gastos)). `/ayuda` shows the welcome
again. `/zona America/Bogota` sets the time zone of the agenda and the reports
(default `America/Panama`).

## Logging expenses and income (no LLM)

A message with exactly one amount is registered by code, without the LLM (zero
tokens): `gasto 2 usd cafe`, `2 usd cafe`, `cafe 2000cop gasto`,
`2000 cop cafe`, `cafe 5`, `$3.50 uber`, `1.234,56 cop arriendo`,
`1000usd ingreso`, `ingreso 1000 salario`, `+500 salario`, `-12 lunch`,
`-12 午饭`.

- **Type:** `ingreso` / `income` / `收入` or a leading `+` make it income;
  `gasto` / `expense` / `支出`, a leading `-` or any other words make it an
  expense. A bare amount (`5`, `5 usd`) is not guessed: the bot asks with
  Gasto / Ingreso buttons and registers on the tap.
- **Currency:** an ISO code next to the amount (USD, COP, EUR, MXN, PEN, CLP,
  ARS, BRL, GBP, CAD, PAB), `$`, `€`, `dollars` or `美元`; none means USD. The
  ledger converts to USD. `2,000` / `2.000` are thousands, `2,5` is 2.5.
- **Category:** the other words are the note; keywords in the three languages
  pick the category (`cafe` / `coffee` / `咖啡` → restaurantes, `uber` /
  `打车` → transporte, `groceries` / `超市` → supermercado…), else `otros`.
  Chinese keywords match inside a word (`买咖啡`).
- **To the LLM:** two amounts, questions, dates or times in any of the three
  languages (`mañana a las 4`, `16:00`, `lunes`, `tomorrow`, `how much`,
  `明天`, `多少`). In free text the LLM registers, edits and voids the same way
  ("el último era 3 dólares, no 5").

Every registration answers with the entry as stored, category included, and how
to fix it:

```
−12.00 USD · Almuerzo · Restaurantes
¿Algo mal? Responde: editar: 15 almuerzo restaurantes
```

## Correcting

- **`editar:`** (also `edit:` / `修改:`) followed by what is right fixes the
  **last** movement, without the LLM: amount, currency, category (by name in
  any of the three languages) and note, in any order, separated by spaces, `·`
  or `/`. `editar: 15`, `editar: transporte`, `editar: 20 cop`,
  `edit: 15 lunch Restaurants`.
- **`/ultimos`:** the last 5 movements, numbered (1 = the most recent).
- **`/editar <n> <amount>[currency]`:** `/editar 1 3usd`, `/editar 2 2000 cop`.
- **`/anular <n>`:** asks with Confirmar / Cancelar buttons, then voids it.

Nothing is edited or deleted in place: a correction writes a negative `reverso`
of the old row plus a new row (see [DATA.md](DATA.md)).

## Dashboard (Visor de gastos)

`/tablero` (and `/start`) pins a **Visor de gastos** button in the chat and sets
it as the chat's menu button. It opens a Telegram Mini App with the month:
income, spend, savings rate against the 20% target, spend by category and per
day, and the last 15 movements; ← → move between months. It is shown in the
user's language.

Nothing sensitive travels in the URL. `assistant-api` serves the shell at `/visor`; the
page posts Telegram's signed `initData` to `/visor/datos`, which checks the
Ed25519 signature with Telegram's public key and `TELEGRAM_BOT_ID` (the number
before `:` in the bot token, not a secret), so the api never holds the bot
token. Data older than 24 h, signed for another bot, tampered with or from a
non-user gets a 403.

## Scheduled messages

Each one goes out in the user's own time zone (an hourly `tick` job in UTC
picks who is due):

- **07:00:** the agenda of the day and yesterday's spend.
- **22:00:** `Tus gastos hoy: 12.49 USD.` (income excluded) or
  `Hoy no registraste gastos.`, then `Para más detalles revisa tu tablero:
  Visor de gastos 📊`.
- **Sunday 22:00:** the same, plus the week's spend, top categories and,
  against the month's income, the 20% to save and what is left per week, in
  one message.

## GIF reactions (`/fun`)

`/fun` toggles GIF replies per user (`users.fun`, **off by default**). With it
on, a registration answers with a random reaction GIF instead of the text; the
text is the fallback when no GIF fits or sending it fails.

One shared catalog, curated by the owner, serves every user:
`gif_catalog/{tipo}` (`gasto` | `ingreso`) maps a key (a gasto category such as
`restaurantes`, an ingreso source such as `salario`, or `general`) to up to 20
Telegram file_ids. The movement's category or source picks the GIFs, else
`general`. Owner only (anyone else gets a one-line refusal):

- Send a GIF with the caption `gasto`, `gasto restaurantes`, `ingreso` or
  `ingreso salario` (no key = `general`), or reply to a GIF with
  `/gif gasto restaurantes`.
- `/gif borrar` replying to a GIF removes it from every key.
- `/gif` alone lists the counts per type and key.

Telegram file_ids are per bot, so staging (its own Firestore database and bot)
and production keep separate catalogs; curate each from its own bot. Old
per-user libraries move with
`uv run python -m assistant.admin migrate-gifs <owner_chat_id>`.

## Agenda

Natural language works in any of the three languages: "reunión con Ana mañana
3pm", "remind me to pay the power bill Friday 9am", "我周四有空吗？".

- **Conflicts:** before scheduling, the code checks the agenda and the busy
  blocks of a connected calendar (`/conectar <url>`); on a clash it asks with
  buttons whether to schedule anyway. "¿Qué tengo libre el jueves?" lists free
  slots between 08:00 and 20:00.
- **`/calendario`** lists the next 7 days, one line per day, without the LLM:
  `Jue 2 · 09:00 Dentista · 16:00 Llamada banco`.
- **Reminders** arrive on Telegram at the exact minute (Cloud Tasks, at
  `start - reminder_min`). Tasks are scheduled at most 30 days ahead; later
  ones are queued by the morning digest once within 30 days. Cancelling deletes
  the task.

### Google Calendar (instant)

Share your Google Calendar with
`assistant-worker@jd-botjonh.iam.gserviceaccount.com` (Settings → your calendar
→ Share with specific people → **Make changes to events**), then send
`/vincular <calendar_id>` (for a personal account the primary calendar id is
your Gmail address; `/vincular off` unlinks). From then on every create and
cancel is mirrored there within seconds, and conflicts read that calendar
directly. Firestore stays the source of truth; the mirror is best effort.

### Subscribe from your calendar app

`/calendario enlace` replies with your private URL (`$API_URL/ics/<token>.ics`);
anyone with it can read your agenda, so `/calendario nuevo` replaces it and
revokes the old one.

- **Google Calendar (web):** Other calendars → **+** → **From URL** → paste the
  link → **Add calendar**.
- **Apple Calendar:** iPhone: Settings → Calendar → Accounts → Add Account →
  Other → Add Subscribed Calendar. Mac: File → New Calendar Subscription.
- **Outlook:** Add calendar → Subscribe from web → paste the link → Import.

Subscriptions are read-only and refreshed by the app, not pushed: Google
refreshes every ~8–24 h, so a new appointment may take hours to show there. The
Telegram reminder does not depend on that refresh.

## Command list

| Command | What it does |
|---|---|
| `/tablero` | Pins the Visor de gastos |
| `/ultimos` | Last 5 movements |
| `/editar <n> <amount>` | Fixes movement `n` |
| `/anular <n>` | Voids movement `n` (with confirmation) |
| `/calendario [enlace\|nuevo]` | Next 7 days; private ICS link |
| `/fun` | GIF replies on or off |
| `/zona <IANA zone>` | Time zone |
| `/vincular <id\|off>` | Mirror to Google Calendar |
| `/conectar <url\|off>` | Warn about clashes with an iCal calendar |
| `/ayuda` | The welcome |
| `/invitar <name>`, `/usuarios`, `/gif` | Owner only, not in the menu |

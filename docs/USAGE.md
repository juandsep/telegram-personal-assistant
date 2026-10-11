# Using Juani

Everything a user can do with Juani, in detail. Back to the
[README](../README.md).

## Languages

Juani speaks Spanish, English, Chinese, French and German. The language comes from the
`language_code` of the user's Telegram app (it follows the phone unless changed
in Telegram) and is saved as `users.idioma` whenever it changes, so the
scheduled messages use it too. Any other language falls back to English.
French and German get every reply, report and the dashboard; the quick
category keywords stay in Spanish, English and Chinese, so a French or German
entry without one goes to the LLM, which picks the category.

`src/assistant/i18n.py` holds every reply, the reports, the dashboard and the
category names (stored keys stay Spanish, so no data changes with the
language). The LLM is told to answer in the user's language. Commands keep their
Spanish names (`/tablero`, `/ultimos`…) in every language. Only the owner-only
commands (`/invitar`, `/usuarios`, `/catalogo`) answer in Spanish.

## Getting started

Only people the owner lets in can use the bot, in one of two ways:

- **Access request:** a stranger taps Start (a bare `/start`). The bot tells
  them it asked, and the owner gets `Nueva solicitud de acceso: <name> @user`
  with ✅ Aceptar / ❌ Rechazar. Accepting creates the beta and tells them to
  tap `/start`; rejecting tells them they may ask again in 10 days. At most
  one new request a day in total ("try tomorrow" after that), none past 100
  users, and a pending request is not repeated. Anything else from a stranger
  is dropped without an answer.
- **Invite:** the owner sends `/invitar <name>` and forwards the single-use
  `t.me` link (valid 24 h).

Opening the invite link, or `/start` once accepted, sends `/start`,
which creates the user, shows Juani's short welcome with a **🗺️ Guía completa**
button (this guide's site) and sets the Visor de gastos as the chat's menu
button (see [Dashboard](#dashboard-visor-de-gastos)), then asks for the
currency with a **💱 Elegir moneda** button that opens a small Mini App: a list
(🇺🇸 USD · 🇪🇺 EUR · 🇬🇧 GBP · 🇨🇴 COP · 🇨🇳 CNY, with the current one selected)
and the phone's local time. Saving stores the currency and the phone's time
zone, closes the app and confirms in the chat ("✓ Moneda: USD. Tu hora: 14:55
(America/Panama)"). `/ayuda` shows
the welcome again.

`/usuarios` lists everyone with access, how many were active in the last 7
days and each one's last active day (`hoy`, `ayer`, `hace N días`, `sin uso`),
with a button to revoke each beta.

**Data retention:** revoking removes access at once and erases the person's
data 30 days later (letting them in again before that keeps it). A beta who
does not use the bot for 60 days loses data and access; on day 53 the bot
warns them, and any message restarts the count. The owner is never erased.
The daily ledger CSV keeps their rows as anonymous history (a random alias, no
note). Weekly JSON backups age out within 90 days.

**Currency:** `/moneda` (or `moneda` / `currency`) opens the same Mini App;
`/moneda COP` sets it directly. Every amount the bot shows (replies, scheduled
messages, budgets, the dashboard, the LLM's answers) is in that currency, and an
amount typed without a currency is taken in it. The ledger itself stays in USD.
Travelling does not need a currency change: write the amount in the local
currency (`20 eur cena`, `£12 taxi`, `15 libras`) and it is converted at the
day's rate.

**Time zone:** Telegram never tells a bot the user's zone, so the phone's zone
is read whenever a Mini App opens: the currency picker and the Visor de gastos
store it (a trip is picked up the next time either opens). `/moneda COP` typed
as text only sets a first guess when no zone is set yet (COP →
America/Bogota, EUR → Europe/Madrid, GBP → Europe/London, CNY → Asia/Shanghai,
USD → America/New_York).
`/zona America/Bogota` is a manual override, not in the menu. Without any, the
default is `America/Panama`.

Commands also work as a plain word, without `/`, in any case and with or
without accents, when the word is the whole message: `tablero` / `dashboard`,
`tablero fijar` / `dashboard pin`, `resumen` / `summary`, `ultimos` / `last`,
`ayuda` / `help`, `calendario` / `calendar` / `agenda`, `fun`, `moneda` /
`currency`. Anything longer
(`15 cafe`, `ayuda con el arriendo`) is handled as usual.

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
  ARS, BRL, GBP, CAD, PAB, CNY), `$`, `€`, `dollars` or `美元`; none means the
  user's currency (`/moneda`). The ledger converts to USD at the day's rate.
  `2,000` / `2.000` are thousands, `2,5` is 2.5.
- **Category:** the other words are the note; keywords in the three languages
  pick the category (`cafe` / `coffee` / `咖啡` → restaurantes, `uber` /
  `打车` → transporte, `groceries` / `超市` → supermercado…), else `otros`.
  Chinese keywords match inside a word (`买咖啡`).
- **To the LLM:** two amounts, questions, dates or times in any of the three
  languages (`mañana a las 4`, `16:00`, `lunes`, `tomorrow`, `how much`,
  `明天`, `多少`). In free text the LLM registers, edits and voids the same way
  ("el último era 3 dólares, no 5").

Every registration answers with the entry in the user's currency, category
included, and the amount as typed when it was another currency:

```
−12.00 USD · Almuerzo · Restaurantes
−48000.00 COP · Uber · Transporte (12 USD)
```

## Correcting

There is no editing: to fix a movement, void it and write it again. Editing a
message already sent changes nothing; the bot answers the edit with that hint.

- **`/ultimos`:** the last 5 movements, numbered (1 = the most recent).
- **`/anular <n>`:** asks with Confirmar / Cancelar buttons, then voids it.

Nothing is deleted in place: voiding writes a negative `reverso` of the row
(see [DATA.md](DATA.md)).

A word glued to the amount is split off (`-5cafe` is `-5 cafe`, `3euros` is
`3 euros`), unless the token already reads as an amount with its currency
(`5usd`).

## Dashboard (Visor de gastos)

`/tablero` sends a message with a **Visor de gastos** button; `/tablero fijar`
(`dashboard pin`) also pins it at the top of the chat. The Visor shows only
when asked: `/start` and `/reset` put the menu button back to Telegram's default
and unpin the chat. It opens a Telegram Mini App with the month:
income, spend, savings rate against the 20% target, spend by category and per
day, and the last 15 movements; ← → move between months. It is shown in the
user's language and currency, and sends the phone's time zone (`X-Tz`), stored
when it changed.

Nothing sensitive travels in the URL. The service serves the shell at `/visor`; the
page posts Telegram's signed `initData` to `/visor/datos`, which checks the
Ed25519 signature with Telegram's public key and `TELEGRAM_BOT_ID` (the number
before `:` in the bot token, not a secret), so the api never holds the bot
token. Data older than 24 h, signed for another bot, tampered with or from a
non-user gets a 403.

## Scheduled messages

Each one goes out in the user's own time zone (an hourly `tick` job in UTC
picks who is due):

- **07:00:** the agenda of the day, only when there is something on it.
- **Sunday 18:00:** the week's spend, top categories and, against the month's
  income, the 20% to save and what is left per week, then `Para más detalles
  revisa tu tablero: Visor de gastos 🧭`. Its **🔕 No enviar este resumen**
  button turns it off (`users.resumen_semanal`); `/semanal` (or `semanal` /
  `weekly`) turns it back on or off. There is no daily spending report.

`/resumen` (or `resumen` / `summary`) gives the same on demand, without the LLM:
today's spend and, when there is any spend or income, the week and the month
against income.

## Reactions (`/fun`)

`/fun` toggles reaction replies per user (`users.fun`, **off by default**). With
it on, a registration answers with a random image or GIF instead of the text,
and a meal photo gets one after its reply; the text is the fallback when the
catalog has nothing that fits or sending fails.

One shared catalog, curated by the owner, serves every user. Each item has a
tag `<kind>/<key>`:

- `gasto/<category>` (`gasto/restaurantes`…) and `ingreso/<source>`
  (`ingreso/salario`…): the movement's category or source picks the tag, else
  `gasto/general` or `ingreso/general`.
- `comida/sana`, `comida/meh`, `comida/chatarra`: Gemini's verdict on a meal
  photo.

The owner fills it from the **/catalogo** Mini App (anyone else gets a one-line
refusal): pick an existing tag or type a new one, choose one or more files
(JPEG, PNG, WebP or GIF, 5 MB each; the type is checked by content), upload;
🗑️ on a thumbnail deletes it. Files go to the public-read bucket
`<project>-media` (Telegram fetches them by URL; the bucket cannot be listed)
and each tag lives in Firestore `media/{id}`. Staging and production share the
bucket but each has its own Firestore database, so curate each from its own bot.

## Agenda

The assistant remembers the last few exchanges, including commands and button
taps answered without the LLM, so a follow-up like "¿ya quedó?" after
`/calendario` makes sense to it.

Natural language works in any of the three languages: "reunión con Ana mañana
3pm", "remind me to pay the power bill Friday 9am", "我周四有空吗？".

- **Conflicts:** before scheduling, the code checks the agenda and the busy
  blocks of the connected calendar (see below); on a clash it asks with
  buttons whether to schedule anyway. "¿Qué tengo libre el jueves?" lists free
  slots between 08:00 and 20:00.
- **`/calendario`** lists the next 7 days, one line per day, without the LLM:
  `Jue 2 · 09:00 Dentista · 16:00 Llamada banco`, with a **🪢 Conectar
  calendario** button (or **✂️ Desconectar …** when one is connected).
- **Reminders** arrive on Telegram at the exact minute (Cloud Tasks, at
  `start - reminder_min`). Tasks are scheduled at most 30 days ahead; later
  ones are queued by the morning digest once within 30 days. Cancelling deletes
  the task.

### Connecting your calendar

`calendario` → **🪢 Conectar calendario** → pick one calendar (connecting one
replaces the other; **✂️ Desconectar** or `/calendario off` removes it):

- **Google:** a button opens Google's sign-in (valid 10 minutes); allow access
  to your calendar's events. The bot says when it is done and copies your
  upcoming items. From then on every create and cancel is mirrored to your main
  Google Calendar within seconds, and conflicts read it directly. It works
  both ways: move, rename or delete one of those items in Google and the bot
  follows within the hour (the reminder moves with it). Events you create in
  Google itself show as busy time. The mirror is best effort. Google shows an
  "unverified app" notice: Advanced → Go to Juani.
- **iPhone / Outlook:** **🗓️ Suscribirme** opens your calendar app on your
  private feed (`$API_URL/ics/<token>.ics`, as `webcal://`). Ask "¿ya quedó?" or "is
  my calendar connected?" afterwards: the bot knows when your calendar app last
  read the feed. Anyone with that
  link can read your agenda, so `/calendario nuevo` replaces it and revokes the
  old one. Optionally, paste your calendar's secret iCal link in the chat to
  get clash warnings too (the bot deletes the message): iPhone Calendar →
  calendar info → Public Calendar; Outlook → Settings → Shared calendars →
  Publish; Google → Settings → Integrate calendar → Secret address in iCal
  format.

Subscriptions are read-only and refreshed by the app, not pushed (Outlook and
Google take hours), so a new appointment may take a while to show there. The
Telegram reminder does not depend on that refresh.

## Photos: meals and split checks

Send a photo; Gemini (`GEMINI_MODEL`, default `gemini-3.5-flash-lite`) reads
it once and the photo is not kept. The caption guides it.

- **A meal:** the reply shows the dish, estimated kcal and macros, today's
  total (`🍽️ Arepa · ~300 kcal … Hoy llevas ~900 kcal`) and a 💡 tip that
  balances the day (Gemini sees what you already ate today). Gemini also rates
  the dish healthy, meh or unhealthy: with `/fun` on, a `comida/sana`,
  `comida/meh` or `comida/chatarra` reaction follows. **🗑️ Quitar**
  removes a wrong one. Photo estimates are rough (often ±20–30%): good for
  habits, not for a clinical diet.
- **A receipt:** with the people in the caption (`cena salida 4`) the total is
  split between 4, you included; without them the bot asks with buttons.
  Naming items assigns them (`Ana: pizza; yo: pasta`); the rest is shared, and
  tax or tip scale every share alike. Each share gets a **✅** button to mark
  it paid. No expense is recorded: log your own share as usual.
- **`cuentas`** (or `me deben`, `/cuentas`) lists who still owes you, with the
  ✅ buttons.

The Gemini project runs on the free tier: Google may use the photos to improve
its products. Turn on billing in that project to stop it.

## Talking to Juani

Questions about the bot itself or small talk ("¿cómo te llamas?", "¿quién te
creó?", "gracias") go to the LLM, which answers in one or two warm sentences
without tools. The system prompt (`src/assistant/llm/prompts/system.md`) holds
the identity: the name is Juani, created in September 2026, creator unknown for
now. Change it there; the prompt version bumps on its own.

## Starting over (`/reset`)

`/reset` (or `reset`, `reiniciar`, `borrar todo`) asks first, with
**🧨 Sí, borrar todo** / **Cancelar** buttons. Confirming:

- disconnects a linked calendar (revokes the Google grant),
- deletes the chat's ledger, agenda (pending reminders then fire into nothing),
  LLM history, preferences, settings (currency, time zone, `/fun`) and the
  calendar feed link (`state.reset_user`),
- deletes the chat's recent messages with `deleteMessages`, best effort:
  Telegram lets a bot delete only messages from the last 48 h, so the reply
  points to Telegram's own **Clear history** for older ones.

Access stays (`users.nombre`, `users.rol`), so the user keeps using the bot
from scratch. The daily rate and LLM spend counters also stay, so a reset never
lifts the cap. Events already copied to the user's own Google Calendar and the
nightly backups and ledger CSV exports in GCS are not touched.

## Command list

| Command | What it does |
|---|---|
| `/tablero [fijar]` | The Visor de gastos; `fijar` pins it |
| `/resumen` | Today, the week and the month vs income |
| `/ultimos` | Last 5 movements |
| `/anular <n>` | Voids movement `n` (with confirmation) |
| `/calendario [off\|nuevo]` | Next 7 days and connecting a calendar; `off` disconnects, `nuevo` a new feed link |
| `/cuentas` | Split checks people still owe you, with ✅ buttons |
| `/fun` | Reaction images on or off |
| `/moneda [USD\|EUR\|COP\|CNY]` | Display currency (buttons without a code) |
| `/reset` | Erases all the user's data and recent chat messages (with confirmation) |
| `/zona <IANA zone>` | Time zone (not in the menu) |
| `/ayuda` | The welcome |
| `/invitar <name>`, `/usuarios`, `/catalogo` | Owner only, in the owner's menu alone |

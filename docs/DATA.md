# Data and reporting

How Juani stores money and appointments, and how to analyze them. Back to the
[README](../README.md).

## Finance ledger

Firestore is the source of truth: `ledger/{chat_id}/movimientos/{doc_id}`, one
append-only document per movement with:

| Field | Meaning |
|---|---|
| `fecha` | ISO date |
| `monto` | USD, string with 2 decimals (never a float) |
| `moneda`, `monto_original`, `moneda_original`, `tasa`, `fuente_tasa` | Currency as entered and the rate used |
| `categoria` (gasto) / `fuente` (ingreso) | Stored keys, always in Spanish |
| `tipo_mov` | `gasto` \| `ingreso` |
| `nota` | Free text |
| `batch_id`, `update_id` | The message that wrote it |
| `tipo` | `registro` \| `reverso` |
| `creado` | Server timestamp |

Doc ids make writes idempotent, so a Pub/Sub retry never duplicates a row:
gasto `{update_id}-{i}`, ingreso `{update_id}-i0`, undo `{batch_id}-r{i}`.
Nothing is edited or deleted: undo, `/anular`, `/editar` and `editar:` write
negative `reverso` copies (plus a new `registro` for an edit). Sum `monto` to
net them out.

Users see amounts in `users.moneda` (display only; the ledger stays USD): a row
typed in that currency shows `monto_original` exactly, any other row its `monto`
times that day's rate (`fx/{fecha}_{moneda}`, cached). Sums convert row by row,
so a reverso still cancels its registro.

Categories map to the 50/30/20 rule:

- **necesidades:** vivienda, servicios, supermercado, transporte, salud, deudas
- **ocio:** restaurantes, entretenimiento, compras, viajes, suscripciones, otros
- **ahorro:** ahorro, inversion

Budget advice compares the spend per category with `preferences/{chat_id}`, or
with 50/30/20 of the month's income when there is no budget. Budget caps are
USD; for another display currency they are converted at today's rate, and spend
and income per row as above. It is plain code;
the LLM only phrases the result.

## Export, backup and Looker Studio

Every day from 12:00 UTC the `tick` job exports the previous day's writes
(America/Panama) to
`gs://$BACKUP_BUCKET/ledger/mes=YYYY-MM/YYYY-MM-DD.csv` with the header
`fecha,chat_id,tipo_mov,categoria,monto,moneda,nota,batch_id,tipo`. Files are
create-only and kept forever. The weekly JSON backup of the Firestore
collections lives under `backup/` with a 90-day lifecycle. A `cron/{key}`
marker records each success; a failure is retried at the next hourly tick
without holding back anyone's message.

Terraform creates the BigQuery external table `botjonh.ledger` over those files
(`terraform output bigquery_ledger_table`). To build a dashboard:

1. Open [lookerstudio.google.com](https://lookerstudio.google.com) → **Create**
   → **Data source** → **BigQuery** → project `jd-botjonh` → dataset `botjonh`
   → table `ledger` → **Connect**.
2. Add a calculated field `bucket` for the 50/30/20 rule:

   ```
   CASE
     WHEN categoria IN ("vivienda","servicios","supermercado","transporte","salud","deudas") THEN "necesidades"
     WHEN categoria IN ("ahorro","inversion") THEN "ahorro"
     ELSE "ocio"
   END
   ```

3. Suggested charts (filter `tipo_mov = gasto` unless noted): monthly spend
   trend (time series, `fecha` by month, SUM `monto`); spend by `categoria`
   (bar); 50/30/20 split by `bucket` (pie) next to income
   (`tipo_mov = ingreso`).

## Agenda

`agenda/{chat_id}/eventos/{evento_id}` with `titulo`, `inicio` / `fin` (ISO
with the user's offset, plus `inicio_utc` / `fin_utc` for range queries),
`ubicacion`, `recordatorio_min`, `tipo` (`evento` | `recordatorio`), `estado`
(`activo` | `cancelado`) and `creado`. The id is the Telegram `update_id`, so a
retry never duplicates; cancelling only flips `estado`.

A chat has at most one connected calendar in `preferences/{chat_id}`, encrypted
with Cloud KMS (the chat id as associated data), never in clear:
`gcal_token_enc` (the Google OAuth refresh token, `calendario` → Google) or
`ics_url_enc` (a secret iCal link pasted in the chat). Connecting one removes
the other; `gcal_id` is the legacy shared-calendar id, still served. The ICS feed token lives in
`ics_tokens/{token}` with a pointer in `users.ics_token`.

## Other collections

| Collection | Content | Expiry |
|---|---|---|
| `users/{chat_id}` | `nombre`, `rol` (owner \| beta), `moneda` (display currency: USD \| EUR \| COP \| CNY), `zona_horaria` (unset until guessed from the currency, the phone or `/zona`), `idioma`, `fun`, `last_batch` | — |
| `processed/{update_id}` | Dedup marker | TTL 7 days |
| `invites/{code}` | Single-use invite | TTL 24 h |
| `rate`, `spend` | Per-chat message and LLM spend counters | TTL |
| `pending/{token}` | Confirmation waiting for a button | TTL 10 min |
| `oauth_states/{token}` | `chat_id` of a Google sign-in in progress (single use) | TTL 10 min |
| `history/{chat_id}` | Last 6 LLM turns | — |
| `gif_catalog/{tipo}` | Shared reaction GIFs | — |
| `cron/{key}` | Export and backup success markers | TTL 30 days |

Doc ids contain chat_ids, so they are never logged.

# ruff: noqa: E501  (message texts keep Telegram line breaks)
"""User-facing texts in Spanish, English and Chinese.

The language is Telegram's ``language_code`` of the user's app (it follows the
phone's language unless changed in Telegram), stored as ``users.idioma``.
Anything not English or Chinese falls back to Spanish. Commands keep their
Spanish names (/tablero, /ultimos...) in every language.
"""

from __future__ import annotations

IDIOMAS = ("es", "en", "zh")
NOMBRE = {"es": "español", "en": "English", "zh": "简体中文"}


def idioma(language_code: str | None) -> str:
    """``en-US`` -> en, ``zh-hans`` -> zh, anything else -> es."""
    code = (language_code or "").lower()
    return next((i for i in ("en", "zh") if code.startswith(i)), "es")


TEXTOS: dict[str, dict[str, str]] = {
    "welcome": {
        "es": """Hola 👋 Soy Juani, tu asistente en tu teléfono. Llevo tus gastos, ingresos y agenda. Escríbeme normal:

💸 Gastos e ingresos (todo queda en USD; otras monedas se convierten con la TRM)
• -12 almuerzo · 25000 cop mercado · pan 2, leche 3
• +1500 salario (el + es ingreso) · un monto solo te pregunto
• ¿Algo mal? editar: 15 restaurantes corrige el último · /ultimos, /anular 1
• /fun: te respondo con GIFs (otra vez /fun los apaga)
• Visor de gastos: tu tablero del mes, fijado arriba del chat (/tablero lo fija de nuevo)

📅 Agenda
• reunión con Ana mañana 3pm · recuérdame pagar la luz el viernes 9am
• /calendario: próximos 7 días · ¿qué tengo libre el jueves?
• /vincular tu-correo@gmail.com: copia tus eventos a Google Calendar
• /conectar: avisa choques con tu calendario

🕙 Cada día a las 22:00 te digo cuánto gastaste, y el domingo cómo va la semana.
Tu zona horaria: /zona America/Bogota

/ayuda muestra esto de nuevo.""",
        "en": """Hi 👋 I'm Juani, your assistant on your phone. I track your expenses, income and calendar. Just write to me:

💸 Expenses and income (everything is kept in USD; other currencies are converted)
• -12 lunch · 25000 cop groceries · bread 2, milk 3
• +1500 salary (+ means income) · send just an amount and I'll ask
• Something off? edit: 15 restaurants fixes the last one · /ultimos, /anular 1
• /fun: I answer with GIFs (/fun again turns them off)
• Expense viewer: your monthly dashboard, pinned at the top of the chat (/tablero pins it again)

📅 Calendar
• meeting with Ana tomorrow 3pm · remind me to pay the power bill Friday 9am
• /calendario: next 7 days · am I free on Thursday?
• /vincular your-email@gmail.com: copies your events to Google Calendar
• /conectar: warns about clashes with your calendar

🕙 Every day at 22:00 I tell you what you spent, and on Sunday how your week went.
Your time zone: /zona America/New_York

/ayuda shows this again.""",
        "zh": """你好 👋 我是 Juani，你手机里的助手。我帮你记录支出、收入和日程。直接给我发消息：

💸 支出和收入（全部以 USD 记录，其他货币会自动换算）
• -12 午饭 · 25000 cop 超市 · 面包 2, 牛奶 3
• +1500 工资（+ 表示收入）· 只发金额我会问你
• 有误？修改: 15 餐饮 可更正最后一笔 · /ultimos、/anular 1
• /fun：用 GIF 回复你（再发 /fun 关闭）
• 支出查看器：本月账单面板，已置顶在聊天上方（/tablero 可重新置顶）

📅 日程
• 明天下午3点和 Ana 开会 · 周五上午9点提醒我交电费
• /calendario：未来 7 天 · 我周四有空吗？
• /vincular 你的邮箱@gmail.com：把事件同步到 Google 日历
• /conectar：提醒你与日历冲突的安排

🕙 每天 22:00 我会告诉你当天花了多少，周日告诉你本周情况。
你的时区：/zona Asia/Shanghai

/ayuda 再次显示此说明。""",
    },
    "visor": {"es": "Visor de gastos", "en": "Expense viewer", "zh": "支出查看器"},
    "tablero": {
        "es": "Consulta tu tablero aquí 👇 (también en el botón de menú).",
        "en": "Check your dashboard here 👇 (also in the menu button).",
        "zh": "在这里查看你的账单面板 👇（菜单按钮里也有）。",
    },
    "hint": {
        "es": "Para más detalles revisa tu tablero: Visor de gastos 📊",
        "en": "For more details check your dashboard: Expense viewer 📊",
        "zh": "更多详情请查看你的面板：支出查看器 📊",
    },
    "gastos_hoy": {
        "es": "Tus gastos hoy: {total} USD.",
        "en": "Your spending today: {total} USD.",
        "zh": "你今天的支出：{total} USD。",
    },
    "sin_gastos": {
        "es": "Hoy no registraste gastos.",
        "en": "You didn't log any expenses today.",
        "zh": "你今天没有记录支出。",
    },
    "ayer": {
        "es": "Ayer: {total} USD.",
        "en": "Yesterday: {total} USD.",
        "zh": "昨天：{total} USD。",
    },
    "semana": {
        "es": "Semana {desde}–{hasta}: {total} USD",
        "en": "Week {desde}–{hasta}: {total} USD",
        "zh": "本周 {desde}–{hasta}：{total} USD",
    },
    "top": {"es": "Top: ", "en": "Top: ", "zh": "最多："},
    "sin_ingresos": {
        "es": "Sin ingresos este mes: registra uno (+1000 salario).",
        "en": "No income this month: log one (+1000 salary).",
        "zh": "本月没有收入：记录一笔（+1000 工资）。",
    },
    "mes": {
        "es": "Mes: ingresos {ingresos}, gastos {gastos} USD.",
        "en": "Month: income {ingresos}, expenses {gastos} USD.",
        "zh": "本月：收入 {ingresos}，支出 {gastos} USD。",
    },
    "ahorra": {
        "es": "Ahorra {ahorro} (20%). Te quedan {libre} USD para el mes "
        "(~{semana}/semana).",
        "en": "Save {ahorro} (20%). You have {libre} USD left this month "
        "(~{semana}/week).",
        "zh": "存下 {ahorro}（20%）。本月还剩 {libre} USD（约每周 {semana}）。",
    },
    "pasaste": {
        "es": "Te pasaste {exceso} USD: el ahorro de {ahorro} está en riesgo.",
        "en": "You're {exceso} USD over: your {ahorro} savings are at risk.",
        "zh": "你超支了 {exceso} USD：{ahorro} 的储蓄有风险。",
    },
    "limit": {
        "es": "Llegaste al límite por ahora. Intenta más tarde.",
        "en": "You've reached the limit for now. Try again later.",
        "zh": "暂时已达上限，请稍后再试。",
    },
    "text_only": {
        "es": "Por ahora solo entiendo texto.",
        "en": "For now I only understand text.",
        "zh": "目前我只能理解文字。",
    },
    "failed": {
        "es": "No pude hacerlo, intenta de nuevo.",
        "en": "I couldn't do that, please try again.",
        "zh": "操作失败，请再试一次。",
    },
    # Commands
    "zona_usage": {
        "es": "Uso: /zona <zona IANA>, ej. /zona America/Bogota. Ahora: {zona}.",
        "en": "Usage: /zona <IANA zone>, e.g. /zona America/New_York. Now: {zona}.",
        "zh": "用法：/zona <IANA 时区>，例如 /zona Asia/Shanghai。当前：{zona}。",
    },
    "zona_ok": {
        "es": "✓ Zona horaria: {zona}.",
        "en": "✓ Time zone: {zona}.",
        "zh": "✓ 时区：{zona}。",
    },
    "google_hint": {
        "es": "Google Calendar: Otros calendarios → + → Desde URL, y pega el enlace.",
        "en": "Google Calendar: Other calendars → + → From URL, and paste the link.",
        "zh": "Google 日历：其他日历 → + → 通过网址添加，然后粘贴链接。",
    },
    "edit_usage": {
        "es": "Uso: /editar <n> <monto>[moneda], ej. /editar 1 3usd",
        "en": "Usage: /editar <n> <amount>[currency], e.g. /editar 1 3usd",
        "zh": "用法：/editar <序号> <金额>[货币]，例如 /editar 1 3usd",
    },
    "anular_usage": {
        "es": "Uso: /anular <n>, ej. /anular 1",
        "en": "Usage: /anular <n>, e.g. /anular 1",
        "zh": "用法：/anular <序号>，例如 /anular 1",
    },
    "conectar_hint": {
        "es": "Envíame el enlace iCal secreto de tu calendario. Google: Configuración → tu calendario → Integrar el calendario → Dirección secreta en formato iCal.",
        "en": "Send me your calendar's secret iCal link. Google: Settings → your calendar → Integrate calendar → Secret address in iCal format.",
        "zh": "把你日历的私密 iCal 链接发给我。Google：设置 → 你的日历 → 集成日历 → iCal 格式的私密地址。",
    },
    "vincular_hint": {
        "es": "Comparte tu Google Calendar con {sa} (Hacer cambios en eventos) y envía /vincular <id>. En una cuenta personal el id es tu Gmail.",
        "en": "Share your Google Calendar with {sa} (Make changes to events) and send /vincular <id>. On a personal account the id is your Gmail.",
        "zh": "把你的 Google 日历共享给 {sa}（权限：更改活动），然后发送 /vincular <id>。个人账户的 id 就是你的 Gmail。",
    },
    "no_disponible": {
        "es": "Aún no disponible.",
        "en": "Not available yet.",
        "zh": "暂不可用。",
    },
    "enlace_no_config": {
        "es": "Enlace no configurado.",
        "en": "Link not configured.",
        "zh": "链接未配置。",
    },
    "tablero_no_config": {
        "es": "Tablero no configurado.",
        "en": "Dashboard not configured.",
        "zh": "面板未配置。",
    },
    "cancelado": {"es": "Cancelado.", "en": "Cancelled.", "zh": "已取消。"},
    "fun_on": {
        "es": "🎉 Modo fun activado: te respondo con GIFs. /fun lo apaga.",
        "en": "🎉 Fun mode on: I'll answer with GIFs. /fun turns it off.",
        "zh": "🎉 已开启趣味模式：我会用 GIF 回复。再发 /fun 关闭。",
    },
    "fun_off": {
        "es": "Modo fun apagado: te respondo con el registro.",
        "en": "Fun mode off: I'll answer with the entry.",
        "zh": "已关闭趣味模式：我会回复记录内容。",
    },
    "corregir": {
        "es": "¿Algo mal? Responde: editar: 15 almuerzo restaurantes",
        "en": "Something off? Reply: edit: 15 lunch restaurants",
        "zh": "有误？回复：修改: 15 午饭 餐饮",
    },
    "corregir_usage": {
        "es": "Escribe editar: y lo correcto del último registro: monto, nota y/o categoría. Ej. editar: 15 · almuerzo · restaurantes",
        "en": "Write edit: and what's right for the last entry: amount, note and/or category. E.g. edit: 15 · lunch · restaurants",
        "zh": "发送 修改: 加上最后一笔的正确内容：金额、备注和/或类别。例如 修改: 15 · 午饭 · 餐饮",
    },
    # Ledger
    "positivo": {
        "es": "El monto debe ser mayor que 0.",
        "en": "The amount must be greater than 0.",
        "zh": "金额必须大于 0。",
    },
    "no_encontrado": {
        "es": "No encontré ese movimiento.",
        "en": "I couldn't find that entry.",
        "zh": "找不到那笔记录。",
    },
    "moneda_no": {
        "es": "Moneda no soportada.",
        "en": "Currency not supported.",
        "zh": "不支持该货币。",
    },
    "sin_tasa": {
        "es": "No pude obtener la tasa de {cur}, intenta luego.",
        "en": "I couldn't get the {cur} rate, try again later.",
        "zh": "无法获取 {cur} 汇率，请稍后再试。",
    },
    "anulado": {
        "es": "✓ anulado: {mov}",
        "en": "✓ voided: {mov}",
        "zh": "✓ 已作废：{mov}",
    },
    "editado": {
        "es": "✓ editado: {mov}",
        "en": "✓ edited: {mov}",
        "zh": "✓ 已修改：{mov}",
    },
    "nada_deshacer": {
        "es": "Nada que deshacer.",
        "en": "Nothing to undo.",
        "zh": "没有可撤销的操作。",
    },
    "lote_no": {
        "es": "Lote no encontrado.",
        "en": "Batch not found.",
        "zh": "找不到该批记录。",
    },
    "deshecho": {
        "es": "↩ deshecho: {n} fila(s)",
        "en": "↩ undone: {n} row(s)",
        "zh": "↩ 已撤销：{n} 条",
    },
    "ya_deshecho": {
        "es": "Ese lote ya estaba deshecho.",
        "en": "That batch was already undone.",
        "zh": "该批记录已撤销过。",
    },
    "sin_movs": {"es": "Sin movimientos.", "en": "No entries.", "zh": "没有记录。"},
    # Budgets
    "dentro": {
        "es": "Dentro del presupuesto.",
        "en": "Within budget.",
        "zh": "在预算之内。",
    },
    "exceso": {
        "es": "Exceso en {cat}{regla}: {gastado} de {cap} USD (+{extra}). Recorta ahí primero.",
        "en": "Over in {cat}{regla}: {gastado} of {cap} USD (+{extra}). Cut there first.",
        "zh": "{cat}{regla}超支：{gastado} / {cap} USD（+{extra}）。先从这里削减。",
    },
    "sin_presupuesto": {
        "es": "Sin presupuesto ni ingresos del mes para comparar.",
        "en": "No budget or income this month to compare with.",
        "zh": "本月没有预算或收入可供比较。",
    },
    # Agenda and calendars
    "sin_7_dias": {
        "es": "Sin nada en 7 días.",
        "en": "Nothing in the next 7 days.",
        "zh": "未来 7 天没有安排。",
    },
    "dias": {
        "es": "Lun Mar Mié Jue Vie Sáb Dom",
        "en": "Mon Tue Wed Thu Fri Sat Sun",
        "zh": "周一 周二 周三 周四 周五 周六 周日",
    },
    "gcal_sin_acceso": {
        "es": "No tengo acceso. Comparte el calendario con {sa} (Hacer cambios en eventos).",
        "en": "I don't have access. Share the calendar with {sa} (Make changes to events).",
        "zh": "我没有访问权限。请把日历共享给 {sa}（权限：更改活动）。",
    },
    "sin_eventos": {"es": "Sin eventos.", "en": "No events.", "zh": "没有活动。"},
    "sin_huecos": {
        "es": "Sin huecos libres.",
        "en": "No free slots.",
        "zh": "没有空闲时段。",
    },
    "evento_no": {
        "es": "Evento no encontrado.",
        "en": "Event not found.",
        "zh": "找不到该活动。",
    },
    "evento_cancelado": {
        "es": "✓ evento cancelado",
        "en": "✓ event cancelled",
        "zh": "✓ 活动已取消",
    },
    "enlace_invalido": {
        "es": "Enlace no válido.",
        "en": "Invalid link.",
        "zh": "链接无效。",
    },
    "cal_ilegible": {
        "es": "No pude leer ese calendario.",
        "en": "I couldn't read that calendar.",
        "zh": "无法读取该日历。",
    },
    "cal_desconectado": {
        "es": "Calendario desconectado.",
        "en": "Calendar disconnected.",
        "zh": "日历已断开。",
    },
    "cal_conectado": {
        "es": "✓ Calendario conectado.",
        "en": "✓ Calendar connected.",
        "zh": "✓ 日历已连接。",
    },
    "gcal_desvinculado": {
        "es": "Google Calendar desvinculado.",
        "en": "Google Calendar unlinked.",
        "zh": "已取消关联 Google 日历。",
    },
    "gcal_id_invalido": {
        "es": "Id de calendario no válido.",
        "en": "Invalid calendar id.",
        "zh": "日历 id 无效。",
    },
    "gcal_no_verifica": {
        "es": "No pude verificar el calendario, intenta luego.",
        "en": "I couldn't verify the calendar, try again later.",
        "zh": "无法验证该日历，请稍后再试。",
    },
    "gcal_vinculado": {
        "es": "✓ Google Calendar vinculado ({n} eventos copiados).",
        "en": "✓ Google Calendar linked ({n} events copied).",
        "zh": "✓ 已关联 Google 日历（已复制 {n} 个活动）。",
    },
    # Bot profile (python -m assistant.admin bot-profile)
    "bot_description": {
        "es": "Hola, soy Juani 👋 Tu asistente de gastos y agenda.\n\n💸 Escribe -12 almuerzo y lo registro al instante.\n📊 Mira tu mes en el Visor de gastos.\n📅 Agenda y recordatorios en lenguaje natural.\n🌎 Hablo español, inglés y chino.\n\nSolo por invitación.",
        "en": "Hi, I'm Juani 👋 Your expense and calendar assistant.\n\n💸 Write -12 lunch and I log it right away.\n📊 See your month in the Expense viewer.\n📅 Calendar and reminders in plain language.\n🌎 I speak English, Spanish and Chinese.\n\nInvitation only.",
        "zh": "你好，我是 Juani 👋 你的记账和日程助手。\n\n💸 发送 -12 午饭，我马上记下。\n📊 在支出查看器里查看本月账单。\n📅 用自然语言管理日程和提醒。\n🌎 我会说中文、英语和西班牙语。\n\n仅限邀请使用。",
    },
    "bot_about": {
        "es": "Juani: tus gastos, ingresos y agenda por chat. Escribe -12 almuerzo y listo 📊",
        "en": "Juani: your expenses, income and calendar by chat. Write -12 lunch and done 📊",
        "zh": "Juani：用聊天记录支出、收入和日程。发送 -12 午饭 即可 📊",
    },
    "cmd_tablero": {
        "es": "Fija tu Visor de gastos del mes",
        "en": "Pin your monthly Expense viewer",
        "zh": "置顶本月支出查看器",
    },
    "cmd_ultimos": {
        "es": "Tus últimos 5 movimientos",
        "en": "Your last 5 entries",
        "zh": "最近 5 笔记录",
    },
    "cmd_editar": {
        "es": "Corrige un movimiento: /editar 1 3usd",
        "en": "Fix an entry: /editar 1 3usd",
        "zh": "修改记录：/editar 1 3usd",
    },
    "cmd_anular": {
        "es": "Anula un movimiento: /anular 1",
        "en": "Void an entry: /anular 1",
        "zh": "作废记录：/anular 1",
    },
    "cmd_calendario": {
        "es": "Tu agenda de los próximos 7 días",
        "en": "Your calendar for the next 7 days",
        "zh": "未来 7 天的日程",
    },
    "cmd_fun": {
        "es": "Activa o apaga las respuestas con GIFs",
        "en": "Turn GIF replies on or off",
        "zh": "开启或关闭 GIF 回复",
    },
    "cmd_zona": {
        "es": "Tu zona horaria: /zona America/Bogota",
        "en": "Your time zone: /zona America/New_York",
        "zh": "你的时区：/zona Asia/Shanghai",
    },
    "cmd_vincular": {
        "es": "Copia tus eventos a Google Calendar",
        "en": "Copy your events to Google Calendar",
        "zh": "把活动同步到 Google 日历",
    },
    "cmd_conectar": {
        "es": "Avisa choques con tu calendario",
        "en": "Warn about clashes with your calendar",
        "zh": "提醒与日历冲突",
    },
    "cmd_ayuda": {
        "es": "Cómo usar a Juani",
        "en": "How to use Juani",
        "zh": "如何使用 Juani",
    },
    # Web dashboard
    "meses": {
        "es": "enero febrero marzo abril mayo junio julio agosto septiembre "
        "octubre noviembre diciembre",
        "en": "January February March April May June July August September "
        "October November December",
        "zh": "1月 2月 3月 4月 5月 6月 7月 8月 9月 10月 11月 12月",
    },
    "d_titulo": {
        "es": "Tablero de {mes}",
        "en": "Dashboard · {mes}",
        "zh": "{mes} 账单",
    },
    "d_usd": {"es": "Montos en USD.", "en": "Amounts in USD.", "zh": "金额单位：USD。"},
    "d_antes": {"es": "← Anterior", "en": "← Previous", "zh": "← 上个月"},
    "d_despues": {"es": "Siguiente →", "en": "Next →", "zh": "下个月 →"},
    "d_ingresos": {"es": "Ingresos", "en": "Income", "zh": "收入"},
    "d_gastos": {"es": "Gastos", "en": "Expenses", "zh": "支出"},
    "d_ahorro": {"es": "Ahorro", "en": "Savings", "zh": "结余"},
    "d_tasa": {"es": "Tasa de ahorro", "en": "Savings rate", "zh": "储蓄率"},
    "d_meta": {
        "es": "Meta 20%: {meta} USD",
        "en": "20% goal: {meta} USD",
        "zh": "20% 目标：{meta} USD",
    },
    "d_sin_ingresos": {
        "es": "Sin ingresos este mes",
        "en": "No income this month",
        "zh": "本月没有收入",
    },
    "d_por_cat": {
        "es": "Gastos por categoría",
        "en": "Expenses by category",
        "zh": "按类别支出",
    },
    "d_sin_gastos": {"es": "Sin gastos.", "en": "No expenses.", "zh": "没有支出。"},
    "d_diario": {"es": "Gasto diario", "en": "Daily spending", "zh": "每日支出"},
    "d_ultimos": {
        "es": "Últimos {n} movimientos",
        "en": "Last {n} entries",
        "zh": "最近 {n} 笔记录",
    },
    "d_sin_movs": {
        "es": "Sin movimientos.",
        "en": "No entries.",
        "zh": "没有记录。",
    },
}


# Stored category and 50/30/20 bucket keys (always Spanish) as shown to the user.
CATEGORIAS: dict[str, dict[str, str]] = {
    "vivienda": {"es": "Arriendo", "en": "Housing", "zh": "住房"},
    "servicios": {"es": "Servicios", "en": "Utilities", "zh": "水电网"},
    "supermercado": {"es": "Mercado", "en": "Groceries", "zh": "超市"},
    "transporte": {"es": "Transporte", "en": "Transport", "zh": "交通"},
    "salud": {"es": "Salud", "en": "Health", "zh": "医疗"},
    "deudas": {"es": "Deudas", "en": "Debt", "zh": "债务"},
    "restaurantes": {"es": "Restaurantes", "en": "Restaurants", "zh": "餐饮"},
    "entretenimiento": {"es": "Entretenimiento", "en": "Entertainment", "zh": "娱乐"},
    "compras": {"es": "Compras", "en": "Shopping", "zh": "购物"},
    "viajes": {"es": "Viajes", "en": "Travel", "zh": "旅行"},
    "suscripciones": {"es": "Suscripciones", "en": "Subscriptions", "zh": "订阅"},
    "otros": {"es": "Otros", "en": "Other", "zh": "其他"},
    "ahorro": {"es": "Ahorro", "en": "Savings", "zh": "储蓄"},
    "inversion": {"es": "Inversión", "en": "Investment", "zh": "投资"},
    "necesidades": {"es": "Necesidades", "en": "Needs", "zh": "必需"},
    "ocio": {"es": "Ocio", "en": "Wants", "zh": "休闲"},
}


def categoria(lang: str, clave: str) -> str | None:
    """A stored category key in ``lang``; None for free text (a note)."""
    nombres = CATEGORIAS.get(clave)
    return nombres.get(lang, nombres["es"]) if nombres else None


def t(lang: str, clave: str, **valores: object) -> str:
    textos = TEXTOS[clave]
    return textos.get(lang, textos["es"]).format(**valores)

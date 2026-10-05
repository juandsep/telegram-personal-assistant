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

💸 -12 almuerzo · 25000 cop mercado · +1500 salario (el + es ingreso)
✏️ editar: 15 restaurantes corrige el último
📊 tablero: tu mes · resumen: hoy, semana y mes
📅 reunión con Ana mañana 3pm · calendario: tu agenda
🎉 fun: te respondo con GIFs

Escribe la palabra sola, sin "/". ayuda muestra esto de nuevo.""",
        "en": """Hi 👋 I'm Juani, your assistant on your phone. I track your expenses, income and calendar. Just write to me:

💸 -12 lunch · 25000 cop groceries · +1500 salary (+ means income)
✏️ edit: 15 restaurants fixes the last one
📊 dashboard: your month · summary: today, week and month
📅 meeting with Ana tomorrow 3pm · calendar: your agenda
🎉 fun: I answer with GIFs

Just write the word, no "/". help shows this again.""",
        "zh": """你好 👋 我是 Juani，你手机里的助手。我帮你记录支出、收入和日程。直接给我发消息：

💸 -12 午饭 · 25000 cop 超市 · +1500 工资（+ 表示收入）
✏️ 修改: 15 餐饮 可更正最后一笔
📊 dashboard：本月账单 · summary：今天、本周和本月
📅 明天下午3点和 Ana 开会 · calendar：你的日程
🎉 fun：用 GIF 回复你

直接发送单词，不用 "/"。help 再次显示此说明。""",
    },
    "guia": {"es": "📖 Guía completa", "en": "📖 Full guide", "zh": "📖 完整指南"},
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
        "es": "Tus gastos hoy: {total} {moneda}.",
        "en": "Your spending today: {total} {moneda}.",
        "zh": "你今天的支出：{total} {moneda}。",
    },
    "sin_gastos": {
        "es": "Hoy no registraste gastos.",
        "en": "You didn't log any expenses today.",
        "zh": "你今天没有记录支出。",
    },
    "ayer": {
        "es": "Ayer: {total} {moneda}.",
        "en": "Yesterday: {total} {moneda}.",
        "zh": "昨天：{total} {moneda}。",
    },
    "semana": {
        "es": "Semana {desde}–{hasta}: {total} {moneda}",
        "en": "Week {desde}–{hasta}: {total} {moneda}",
        "zh": "本周 {desde}–{hasta}：{total} {moneda}",
    },
    "top": {"es": "Top: ", "en": "Top: ", "zh": "最多："},
    "sin_ingresos": {
        "es": "Sin ingresos este mes: registra uno (+1000 salario).",
        "en": "No income this month: log one (+1000 salary).",
        "zh": "本月没有收入：记录一笔（+1000 工资）。",
    },
    "mes": {
        "es": "Mes: ingresos {ingresos}, gastos {gastos} {moneda}.",
        "en": "Month: income {ingresos}, expenses {gastos} {moneda}.",
        "zh": "本月：收入 {ingresos}，支出 {gastos} {moneda}。",
    },
    "ahorra": {
        "es": "Ahorra {ahorro} (20%). Te quedan {libre} {moneda} para el mes "
        "(~{semana}/semana).",
        "en": "Save {ahorro} (20%). You have {libre} {moneda} left this month "
        "(~{semana}/week).",
        "zh": "存下 {ahorro}（20%）。本月还剩 {libre} {moneda}（约每周 {semana}）。",
    },
    "pasaste": {
        "es": "Te pasaste {exceso} {moneda}: el ahorro de {ahorro} está en riesgo.",
        "en": "You're {exceso} {moneda} over: your {ahorro} savings are at risk.",
        "zh": "你超支了 {exceso} {moneda}：{ahorro} 的储蓄有风险。",
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
    "moneda_pregunta": {
        "es": "¿En qué moneda quieres ver tus montos? Puedes cambiarla luego con moneda.",
        "en": "Which currency do you want to see your amounts in? Change it later with currency.",
        "zh": "你想用哪种货币查看金额？之后可以发送 currency 更改。",
    },
    "moneda_ok": {
        "es": "✓ Moneda: {moneda}. Tus montos se muestran en {moneda}.",
        "en": "✓ Currency: {moneda}. Your amounts show in {moneda}.",
        "zh": "✓ 货币：{moneda}。你的金额将以 {moneda} 显示。",
    },
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
        "es": "Exceso en {cat}{regla}: {gastado} de {cap} {moneda} (+{extra}). Recorta ahí primero.",
        "en": "Over in {cat}{regla}: {gastado} of {cap} {moneda} (+{extra}). Cut there first.",
        "zh": "{cat}{regla}超支：{gastado} / {cap} {moneda}（+{extra}）。先从这里削减。",
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
    "gcal_vinculado": {
        "es": "✓ Google Calendar conectado ({n} eventos copiados). Tus citas nuevas aparecerán ahí y te aviso si chocan con las de Google.",
        "en": "✓ Google Calendar connected ({n} events copied). New appointments will show up there and I'll warn you about clashes with Google.",
        "zh": "✓ 已连接 Google 日历（已复制 {n} 个活动）。新的安排会出现在那里，与 Google 日历冲突时我会提醒你。",
    },
    "cal_conectar": {
        "es": "🔗 Conectar calendario",
        "en": "🔗 Connect calendar",
        "zh": "🔗 连接日历",
    },
    "cal_desconectar": {
        "es": "🔌 Desconectar {cual}",
        "en": "🔌 Disconnect {cual}",
        "zh": "🔌 断开 {cual}",
    },
    "cal_elige": {
        "es": "¿Qué calendario usas?",
        "en": "Which calendar do you use?",
        "zh": "你用哪个日历？",
    },
    "cal_google": {
        "es": "Toca el botón, elige tu cuenta y permite el acceso a tu calendario. El enlace vale 10 minutos.",
        "en": "Tap the button, pick your account and allow access to your calendar. The link is valid for 10 minutes.",
        "zh": "点击按钮，选择你的账户并允许访问日历。链接 10 分钟内有效。",
    },
    "cal_google_boton": {
        "es": "Conectar con Google",
        "en": "Connect with Google",
        "zh": "连接 Google",
    },
    "cal_ical": {
        "es": "Toca 📅 Suscribirme y acepta: tus citas de Juani aparecerán en tu calendario.\n\nOpcional: para que te avise si una cita choca con las de tu calendario, pégame aquí su enlace iCal secreto (iPhone: app Calendario → calendario → Calendario público; Outlook: Configuración → Calendarios compartidos → Publicar).",
        "en": "Tap 📅 Subscribe and accept: your Juani appointments will show up in your calendar.\n\nOptional: to warn you about clashes with your calendar, paste its secret iCal link here (iPhone: Calendar app → calendar → Public Calendar; Outlook: Settings → Shared calendars → Publish).",
        "zh": "点击 📅 订阅 并确认：你在 Juani 的安排会出现在日历里。\n\n可选：如需提醒与日历中的安排冲突，请把日历的私密 iCal 链接粘贴到这里（iPhone：日历 App → 日历 → 公开日历；Outlook：设置 → 共享日历 → 发布）。",
    },
    "cal_suscribir": {
        "es": "📅 Suscribirme",
        "en": "📅 Subscribe",
        "zh": "📅 订阅",
    },
    "oauth_ok": {
        "es": "✓ Listo, vuelve a Telegram.",
        "en": "✓ Done, go back to Telegram.",
        "zh": "✓ 完成，请回到 Telegram。",
    },
    "oauth_error": {
        "es": "No se pudo conectar. Vuelve a Telegram y prueba otra vez con calendario.",
        "en": "Couldn't connect. Go back to Telegram and try again with calendar.",
        "zh": "连接失败。请回到 Telegram，发送 calendar 再试一次。",
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
        "es": "Tu Visor de gastos del mes (tablero fijar lo fija)",
        "en": "Your monthly Expense viewer (dashboard pin pins it)",
        "zh": "本月支出查看器（dashboard pin 可置顶）",
    },
    "cmd_resumen": {
        "es": "Tus gastos de hoy, la semana y el mes",
        "en": "Your spending today, this week and this month",
        "zh": "今天、本周和本月的支出",
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
        "es": "Tu agenda de 7 días y conectar tu calendario",
        "en": "Your next 7 days and connecting your calendar",
        "zh": "未来 7 天的日程，连接你的日历",
    },
    "cmd_fun": {
        "es": "Activa o apaga las respuestas con GIFs",
        "en": "Turn GIF replies on or off",
        "zh": "开启或关闭 GIF 回复",
    },
    "cmd_moneda": {
        "es": "La moneda en que ves tus montos",
        "en": "The currency your amounts show in",
        "zh": "显示金额所用的货币",
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
    "d_usd": {
        "es": "Montos en {moneda}.",
        "en": "Amounts in {moneda}.",
        "zh": "金额单位：{moneda}。",
    },
    "d_antes": {"es": "← Anterior", "en": "← Previous", "zh": "← 上个月"},
    "d_despues": {"es": "Siguiente →", "en": "Next →", "zh": "下个月 →"},
    "d_ingresos": {"es": "Ingresos", "en": "Income", "zh": "收入"},
    "d_gastos": {"es": "Gastos", "en": "Expenses", "zh": "支出"},
    "d_ahorro": {"es": "Ahorro", "en": "Savings", "zh": "结余"},
    "d_tasa": {"es": "Tasa de ahorro", "en": "Savings rate", "zh": "储蓄率"},
    "d_meta": {
        "es": "Meta 20%: {meta} {moneda}",
        "en": "20% goal: {meta} {moneda}",
        "zh": "20% 目标：{meta} {moneda}",
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

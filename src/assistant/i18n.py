# ruff: noqa: E501  (message texts keep Telegram line breaks)
"""User-facing texts in Spanish, English, Chinese, French, German and Portuguese.

The language is Telegram's ``language_code`` of the user's app (it follows the
phone's language unless changed in Telegram), stored as ``users.idioma``.
Any other language falls back to English. Commands keep their Spanish names
(/tablero, /ultimos...) in every language, and the plain words (dashboard,
summary...) are the English ones outside Spanish. French, German and Portuguese
live in their own tables at the end, merged into ``TEXTS`` and
``CATEGORY_NAMES``.
"""

from __future__ import annotations

LANGS = ("es", "en", "zh", "fr", "de", "pt")
LANG_NAMES = {
    "es": "español",
    "en": "English",
    "zh": "简体中文",
    "fr": "français",
    "de": "Deutsch",
    "pt": "português",
}


def lang_of(language_code: str | None) -> str:
    """``en-US`` -> en, ``zh-hans`` -> zh, ``pt-BR`` -> pt, anything else -> en."""
    code = (language_code or "").lower()
    return next((i for i in LANGS if code.startswith(i)), "en")


TEXTS: dict[str, dict[str, str]] = {
    "welcome": {
        "es": """Hola 🫶 Soy Juani, tu asistente en tu teléfono. Llevo tus gastos, ingresos y agenda. Escríbeme normal:

🪙 -12 almuerzo · 25000 cop mercado · +1500 salario (el + es ingreso)
🧹 /anular 1 quita el último; luego escríbelo bien
🧭 tablero: tu mes · resumen: hoy, semana y mes
🗓️ reunión con Ana mañana 3pm · calendario: tu agenda
📸 foto de tu plato (calorías) o de un recibo con «cena 4» (divido la cuenta) · cuentas: quién te debe
🪅 fun: te respondo con imágenes

Escribe la palabra sola, sin "/". ayuda muestra esto de nuevo.""",
        "en": """Hi 🫶 I'm Juani, your assistant on your phone. I track your expenses, income and calendar. Just write to me:

🪙 -12 lunch · 25000 cop groceries · +1500 salary (+ means income)
🧹 /anular 1 removes the last one; then write it again
🧭 dashboard: your month · summary: today, week and month
🗓️ meeting with Ana tomorrow 3pm · calendar: your agenda
📸 a photo of your meal (calories) or of a receipt with "dinner 4" (I split it) · splits: who owes you
🪅 fun: I answer with images

Just write the word, no "/". help shows this again.""",
        "zh": """你好 🫶 我是 Juani，你手机里的助手。我帮你记录支出、收入和日程。直接给我发消息：

🪙 -12 午饭 · 25000 cop 超市 · +1500 工资（+ 表示收入）
🧹 /anular 1 删除最后一笔，然后重新记录
🧭 dashboard：本月账单 · summary：今天、本周和本月
🗓️ 明天下午3点和 Ana 开会 · calendar：你的日程
📸 餐食照片（热量）或带「晚餐 4」的收据（分账）· splits：谁欠你钱
🪅 fun：用图片回复你

直接发送单词，不用 "/"。help 再次显示此说明。""",
    },
    "guide": {"es": "🗺️ Guía completa", "en": "🗺️ Full guide", "zh": "🗺️ 完整指南"},
    "viewer": {"es": "Visor de gastos", "en": "Expense viewer", "zh": "支出查看器"},
    "dashboard": {
        "es": "Consulta tu tablero aquí 🫳",
        "en": "Check your dashboard here 🫳",
        "zh": "在这里查看你的账单面板 🫳",
    },
    "hint": {
        "es": "Para más detalles revisa tu tablero: Visor de gastos 🧭",
        "en": "For more details check your dashboard: Expense viewer 🧭",
        "zh": "更多详情请查看你的面板：支出查看器 🧭",
    },
    "spent_today": {
        "es": "Tus gastos hoy: {total} {currency}.",
        "en": "Your spending today: {total} {currency}.",
        "zh": "你今天的支出：{total} {currency}。",
    },
    "no_spending": {
        "es": "Hoy no registraste gastos.",
        "en": "You didn't log any expenses today.",
        "zh": "你今天没有记录支出。",
    },
    "yesterday": {
        "es": "Ayer: {total} {currency}.",
        "en": "Yesterday: {total} {currency}.",
        "zh": "昨天：{total} {currency}。",
    },
    "week": {
        "es": "Semana {since}–{until}: {total} {currency}",
        "en": "Week {since}–{until}: {total} {currency}",
        "zh": "本周 {since}–{until}：{total} {currency}",
    },
    "top": {"es": "Top: ", "en": "Top: ", "zh": "最多："},
    "no_income": {
        "es": "Sin ingresos este mes: registra uno (+1000 salario).",
        "en": "No income this month: log one (+1000 salary).",
        "zh": "本月没有收入：记录一笔（+1000 工资）。",
    },
    "month": {
        "es": "Mes: ingresos {income}, gastos {expenses} {currency}.",
        "en": "Month: income {income}, expenses {expenses} {currency}.",
        "zh": "本月：收入 {income}，支出 {expenses} {currency}。",
    },
    "save": {
        "es": "Ahorra {savings} (20%). Te quedan {left} {currency} para el mes "
        "(~{week}/semana).",
        "en": "Save {savings} (20%). You have {left} {currency} left this month "
        "(~{week}/week).",
        "zh": "存下 {savings}（20%）。本月还剩 {left} {currency}（约每周 {week}）。",
    },
    "overspent": {
        "es": "Te pasaste {excess} {currency}: el ahorro de {savings} está en riesgo.",
        "en": "You're {excess} {currency} over: your {savings} savings are at risk.",
        "zh": "你超支了 {excess} {currency}：{savings} 的储蓄有风险。",
    },
    "access_sent": {
        "es": "Te pedí acceso con el dueño de Juani. Te aviso aquí cuando responda.",
        "en": "I've asked Juani's owner for access. I'll tell you here when they answer.",
        "zh": "我已向 Juani 的主人申请访问权限，有回复时会在这里通知你。",
    },
    "access_wait": {
        "es": "Tu solicitud fue rechazada. Puedes volver a pedir acceso pasados {days} días desde el rechazo.",
        "en": "Your request was declined. You can ask again {days} days after it was declined.",
        "zh": "你的申请被拒绝了。拒绝 {days} 天后可以再次申请。",
    },
    "access_today": {
        "es": "Hoy ya no recibo más solicitudes. Intenta mañana con /start.",
        "en": "I'm not taking more requests today. Try again tomorrow with /start.",
        "zh": "今天不再接受申请，请明天用 /start 再试。",
    },
    "access_full": {
        "es": "Juani no tiene cupo para más usuarios por ahora.",
        "en": "Juani has no room for more users right now.",
        "zh": "Juani 目前没有名额接收更多用户。",
    },
    "access_granted": {
        "es": "✅ Ya tienes acceso. Toca /start para empezar.",
        "en": "✅ You have access now. Tap /start to begin.",
        "zh": "✅ 你已获得访问权限，点 /start 开始。",
    },
    "access_rejected": {
        "es": "Tu solicitud de acceso fue rechazada. Puedes volver a pedirla en {days} días con /start.",
        "en": "Your access request was declined. You can ask again in {days} days with /start.",
        "zh": "你的访问申请被拒绝了。{days} 天后可以用 /start 再次申请。",
    },
    "inactive_warning": {
        "es": "No usas Juani hace un tiempo. En {days} días borro tus datos y tu acceso. Escríbeme cualquier cosa para conservarlos.",
        "en": "You haven't used Juani in a while. In {days} days I'll erase your data and your access. Send me anything to keep them.",
        "zh": "你有一段时间没用 Juani 了。{days} 天后我会删除你的数据和访问权限。发任意消息即可保留。",
    },
    "cal_status_google": {
        "es": "✅ Google Calendar conectado (se sincroniza cada hora).",
        "en": "✅ Google Calendar connected (syncs every hour).",
        "zh": "✅ Google 日历已连接（每小时同步）。",
    },
    "cal_status_import": {
        "es": "✅ Calendario importado por enlace iCal: veo tus ocupados.",
        "en": "✅ Calendar imported by iCal link: I see your busy times.",
        "zh": "✅ 已通过 iCal 链接导入日历：我能看到你的忙碌时间。",
    },
    "cal_status_feed_ok": {
        "es": "✅ Suscripción iPhone/Outlook funcionando: tu calendario la leyó hace {minutes} min.",
        "en": "✅ iPhone/Outlook subscription working: your calendar read it {minutes} min ago.",
        "zh": "✅ iPhone/Outlook 订阅正常：你的日历 {minutes} 分钟前读取过。",
    },
    "cal_status_feed_wait": {
        "es": "⏳ Enlace de suscripción creado, pero tu calendario aún no lo lee. Tras suscribirte puede tardar unos minutos.",
        "en": "⏳ Subscription link created, but your calendar hasn't read it yet. It can take a few minutes after subscribing.",
        "zh": "⏳ 订阅链接已创建，但你的日历还没有读取。订阅后可能需要几分钟。",
    },
    "cal_status_none": {
        "es": "No tienes ningún calendario conectado. Usa calendario para conectarlo.",
        "en": "No calendar connected. Use calendario to connect one.",
        "zh": "你还没有连接日历。用 calendario 连接。",
    },
    "currency_button": {
        "es": "💱 Elegir moneda",
        "en": "💱 Pick currency",
        "zh": "💱 选择货币",
    },
    "save_button": {
        "es": "Guardar",
        "en": "Save",
        "zh": "保存",
    },
    "currency_saved": {
        "es": "✓ Moneda: {currency}. Tu hora: {time} ({zone}).",
        "en": "✓ Currency: {currency}. Your time: {time} ({zone}).",
        "zh": "✓ 货币：{currency}。你的时间：{time}（{zone}）。",
    },
    "edited_hint": {
        "es": "✏️ No leo mensajes editados. Para corregir un movimiento: /anular 1 (el último) y escríbelo de nuevo.",
        "en": "✏️ I don't read edited messages. To fix an entry: /anular 1 (the latest) and write it again.",
        "zh": "✏️ 我不读取编辑过的消息。要更正记录：发送 /anular 1（最近一条）然后重新输入。",
    },
    "weekly_off_button": {
        "es": "🔕 No enviar este resumen",
        "en": "🔕 Stop this summary",
        "zh": "🔕 不再发送此摘要",
    },
    "weekly_off": {
        "es": "🔕 Listo, no te enviaré el resumen de los domingos. semanal lo vuelve a activar.",
        "en": "🔕 Done, no more Sunday summaries. weekly turns them back on.",
        "zh": "🔕 好的，不再发送周日摘要。发送 weekly 可重新开启。",
    },
    "weekly_on": {
        "es": "🔔 Listo, te enviaré el resumen de gastos cada domingo a las 18:00.",
        "en": "🔔 Done, I'll send your spending summary every Sunday at 18:00.",
        "zh": "🔔 好的，每周日 18:00 发送你的支出摘要。",
    },
    "limit": {
        "es": "Llegaste al límite por ahora. Intenta más tarde.",
        "en": "You've reached the limit for now. Try again later.",
        "zh": "暂时已达上限，请稍后再试。",
    },
    "text_only": {
        "es": "Por ahora entiendo texto y fotos.",
        "en": "For now I understand text and photos.",
        "zh": "目前我能理解文字和照片。",
    },
    "failed": {
        "es": "No pude hacerlo, intenta de nuevo.",
        "en": "I couldn't do that, please try again.",
        "zh": "操作失败，请再试一次。",
    },
    # Commands
    "tz_usage": {
        "es": "Uso: /zona <zona IANA>, ej. /zona America/Bogota. Ahora: {tz}.",
        "en": "Usage: /zona <IANA zone>, e.g. /zona America/New_York. Now: {tz}.",
        "zh": "用法：/zona <IANA 时区>，例如 /zona Asia/Shanghai。当前：{tz}。",
    },
    "tz_ok": {
        "es": "✓ Zona horaria: {tz}.",
        "en": "✓ Time zone: {tz}.",
        "zh": "✓ 时区：{tz}。",
    },
    "void_usage": {
        "es": "Uso: /anular <n>, ej. /anular 1",
        "en": "Usage: /anular <n>, e.g. /anular 1",
        "zh": "用法：/anular <序号>，例如 /anular 1",
    },
    "unavailable": {
        "es": "Aún no disponible.",
        "en": "Not available yet.",
        "zh": "暂不可用。",
    },
    "link_not_configured": {
        "es": "Enlace no configurado.",
        "en": "Link not configured.",
        "zh": "链接未配置。",
    },
    "dashboard_not_configured": {
        "es": "Tablero no configurado.",
        "en": "Dashboard not configured.",
        "zh": "面板未配置。",
    },
    "cancelled": {"es": "Cancelado.", "en": "Cancelled.", "zh": "已取消。"},
    "photo_unavailable": {
        "es": "No pude leer la foto ahora. Prueba en un rato.",
        "en": "I couldn't read the photo right now. Try again in a bit.",
        "zh": "暂时无法读取这张照片，请稍后再试。",
    },
    "photo_other": {
        "es": "Mándame la foto de un plato (cuento calorías) o de un recibo con cuántos son, ej. «cena 4» (divido la cuenta).",
        "en": 'Send me a photo of a meal (I count calories) or of a receipt with how many people, e.g. "dinner 4" (I split the bill).',
        "zh": "发给我一张餐食照片（我估算热量），或一张收据并写上人数，例如「晚餐 4」（我来分账）。",
    },
    "meal": {
        "es": "🍽️ {name} · ~{kcal} kcal\nProteína {protein} g · Carbohidratos {carbs} g · Grasa {fat} g\nHoy llevas ~{today} kcal.\n🕐 {times}",
        "en": "🍽️ {name} · ~{kcal} kcal\nProtein {protein} g · Carbs {carbs} g · Fat {fat} g\nToday so far: ~{today} kcal.\n🕐 {times}",
        "zh": "🍽️ {name} · 约 {kcal} 千卡\n蛋白质 {protein} 克 · 碳水 {carbs} 克 · 脂肪 {fat} 克\n今天累计约 {today} 千卡。\n🕐 {times}",
    },
    "meal_remove": {"es": "🗑️ Quitar", "en": "🗑️ Remove", "zh": "🗑️ 删除"},
    "meal_removed": {
        "es": "Listo, la quité.",
        "en": "Done, removed.",
        "zh": "已删除。",
    },
    "split_people": {
        "es": "🧾 {title}: {total} {currency}. ¿Entre cuántos la dividimos (contándote)?",
        "en": "🧾 {title}: {total} {currency}. How many people split it (you included)?",
        "zh": "🧾 {title}：{total} {currency}。几个人分（包括你）？",
    },
    "split": {
        "es": "🧾 {title}: {total} {currency} entre {people}\n{shares}\nToca ✅ cuando te paguen. cuentas muestra lo pendiente.",
        "en": "🧾 {title}: {total} {currency} split {people} ways\n{shares}\nTap ✅ when they pay you. splits shows what's pending.",
        "zh": "🧾 {title}：{total} {currency}，{people} 人分\n{shares}\n收到付款后点 ✅。发送 splits 查看未付。",
    },
    "split_settled": {
        "es": "🎉 {title}: ya te pagaron todos.",
        "en": "🎉 {title}: everyone has paid you.",
        "zh": "🎉 {title}：大家都已付清。",
    },
    "split_pending": {
        "es": "Te deben:",
        "en": "You're owed:",
        "zh": "别人欠你：",
    },
    "split_none": {
        "es": "Nadie te debe nada. 🙌",
        "en": "Nobody owes you anything. 🙌",
        "zh": "没有人欠你钱。🙌",
    },
    "reset_question": {
        "es": "¿Borrar todo? Se eliminan tus gastos, ingresos, agenda, recordatorios, calendario conectado, ajustes y la conversación. No se puede deshacer.",
        "en": "Erase everything? Your expenses, income, agenda, reminders, connected calendar, settings and conversation are deleted. This cannot be undone.",
        "zh": "清除全部？你的支出、收入、日程、提醒、已连接的日历、设置和对话都会被删除。此操作无法撤销。",
    },
    "reset_yes": {
        "es": "🧨 Sí, borrar todo",
        "en": "🧨 Yes, erase all",
        "zh": "🧨 是，全部清除",
    },
    "reset_no": {"es": "Cancelar", "en": "Cancel", "zh": "取消"},
    "reset_done": {
        "es": "✓ Listo, empezamos de cero. Telegram solo me deja borrar mensajes de las últimas 48 h; para los anteriores usa Borrar historial en el chat.",
        "en": "✓ Done, a fresh start. Telegram only lets me delete messages from the last 48 h; for older ones use Clear history in the chat.",
        "zh": "✓ 完成，重新开始。Telegram 只允许我删除 48 小时内的消息；更早的请在聊天中使用“清除历史记录”。",
    },
    "currency_question": {
        "es": "¿En qué moneda quieres ver tus montos? Puedes cambiarla luego con moneda.",
        "en": "Which currency do you want to see your amounts in? Change it later with currency.",
        "zh": "你想用哪种货币查看金额？之后可以发送 currency 更改。",
    },
    "currency_first": {
        "es": "Antes de registrar, elige tu moneda: así tus montos quedan bien.",
        "en": "Before logging anything, pick your currency so your amounts come out right.",
        "zh": "记账前请先选择货币，这样金额才会正确。",
    },
    "currency_ok": {
        "es": "✓ Moneda: {currency}. Tus montos se muestran en {currency}.",
        "en": "✓ Currency: {currency}. Your amounts show in {currency}.",
        "zh": "✓ 货币：{currency}。你的金额将以 {currency} 显示。",
    },
    "fun_on": {
        "es": "🪅 Modo fun activado: te respondo con imágenes y GIFs. /fun lo apaga.",
        "en": "🪅 Fun mode on: I'll answer with images and GIFs. /fun turns it off.",
        "zh": "🪅 已开启趣味模式：我会用图片和 GIF 回复。再发 /fun 关闭。",
    },
    "fun_off": {
        "es": "Modo fun apagado: te respondo con el registro.",
        "en": "Fun mode off: I'll answer with the entry.",
        "zh": "已关闭趣味模式：我会回复记录内容。",
    },
    # Ledger
    "positive": {
        "es": "El monto debe ser mayor que 0.",
        "en": "The amount must be greater than 0.",
        "zh": "金额必须大于 0。",
    },
    "not_found": {
        "es": "No encontré ese movimiento.",
        "en": "I couldn't find that entry.",
        "zh": "找不到那笔记录。",
    },
    "currency_unsupported": {
        "es": "Moneda no soportada.",
        "en": "Currency not supported.",
        "zh": "不支持该货币。",
    },
    "no_rate": {
        "es": "No pude obtener la tasa de {cur}, intenta luego.",
        "en": "I couldn't get the {cur} rate, try again later.",
        "zh": "无法获取 {cur} 汇率，请稍后再试。",
    },
    "voided": {
        "es": "✓ anulado: {entry}",
        "en": "✓ voided: {entry}",
        "zh": "✓ 已作废：{entry}",
    },
    "nothing_to_undo": {
        "es": "Nada que deshacer.",
        "en": "Nothing to undo.",
        "zh": "没有可撤销的操作。",
    },
    "batch_not_found": {
        "es": "Lote no encontrado.",
        "en": "Batch not found.",
        "zh": "找不到该批记录。",
    },
    "undone": {
        "es": "↩ deshecho: {n} fila(s)",
        "en": "↩ undone: {n} row(s)",
        "zh": "↩ 已撤销：{n} 条",
    },
    "already_undone": {
        "es": "Ese lote ya estaba deshecho.",
        "en": "That batch was already undone.",
        "zh": "该批记录已撤销过。",
    },
    "no_entries": {"es": "Sin movimientos.", "en": "No entries.", "zh": "没有记录。"},
    # Budgets
    "within_budget": {
        "es": "Dentro del presupuesto.",
        "en": "Within budget.",
        "zh": "在预算之内。",
    },
    "over_budget": {
        "es": "Exceso en {cat}{rule}: {spent} de {cap} {currency} (+{extra}). Recorta ahí primero.",
        "en": "Over in {cat}{rule}: {spent} of {cap} {currency} (+{extra}). Cut there first.",
        "zh": "{cat}{rule}超支：{spent} / {cap} {currency}（+{extra}）。先从这里削减。",
    },
    "no_budget": {
        "es": "Sin presupuesto ni ingresos del mes para comparar.",
        "en": "No budget or income this month to compare with.",
        "zh": "本月没有预算或收入可供比较。",
    },
    # Agenda and calendars
    "empty_7_days": {
        "es": "Sin nada en 7 días.",
        "en": "Nothing in the next 7 days.",
        "zh": "未来 7 天没有安排。",
    },
    "weekdays": {
        "es": "Lun Mar Mié Jue Vie Sáb Dom",
        "en": "Mon Tue Wed Thu Fri Sat Sun",
        "zh": "周一 周二 周三 周四 周五 周六 周日",
    },
    "no_events": {"es": "Sin eventos.", "en": "No events.", "zh": "没有活动。"},
    "no_free_slots": {
        "es": "Sin huecos libres.",
        "en": "No free slots.",
        "zh": "没有空闲时段。",
    },
    "event_not_found": {
        "es": "Evento no encontrado.",
        "en": "Event not found.",
        "zh": "找不到该活动。",
    },
    "event_cancelled": {
        "es": "✓ evento cancelado",
        "en": "✓ event cancelled",
        "zh": "✓ 活动已取消",
    },
    "invalid_link": {
        "es": "Enlace no válido.",
        "en": "Invalid link.",
        "zh": "链接无效。",
    },
    "cal_unreadable": {
        "es": "No pude leer ese calendario.",
        "en": "I couldn't read that calendar.",
        "zh": "无法读取该日历。",
    },
    "cal_disconnected": {
        "es": "Calendario desconectado.",
        "en": "Calendar disconnected.",
        "zh": "日历已断开。",
    },
    "cal_connected": {
        "es": "✓ Calendario conectado.",
        "en": "✓ Calendar connected.",
        "zh": "✓ 日历已连接。",
    },
    "gcal_linked": {
        "es": "✓ Google Calendar conectado ({n} eventos copiados). Tus citas nuevas aparecerán ahí y te aviso si chocan con las de Google.",
        "en": "✓ Google Calendar connected ({n} events copied). New appointments will show up there and I'll warn you about clashes with Google.",
        "zh": "✓ 已连接 Google 日历（已复制 {n} 个活动）。新的安排会出现在那里，与 Google 日历冲突时我会提醒你。",
    },
    "cal_connect": {
        "es": "🪢 Conectar calendario",
        "en": "🪢 Connect calendar",
        "zh": "🪢 连接日历",
    },
    "cal_disconnect": {
        "es": "✂️ Desconectar {which}",
        "en": "✂️ Disconnect {which}",
        "zh": "✂️ 断开 {which}",
    },
    "cal_choose": {
        "es": "¿Qué calendario usas?",
        "en": "Which calendar do you use?",
        "zh": "你用哪个日历？",
    },
    "cal_google": {
        "es": "Toca el botón, elige tu cuenta y permite el acceso a tu calendario. El enlace vale 10 minutos.",
        "en": "Tap the button, pick your account and allow access to your calendar. The link is valid for 10 minutes.",
        "zh": "点击按钮，选择你的账户并允许访问日历。链接 10 分钟内有效。",
    },
    "cal_google_button": {
        "es": "Conectar con Google",
        "en": "Connect with Google",
        "zh": "连接 Google",
    },
    "cal_ical": {
        "es": "Toca 🗓️ Suscribirme y acepta: tus citas de Juani aparecerán en tu calendario.\n\nOpcional: para que te avise si una cita choca con las de tu calendario, pégame aquí su enlace iCal secreto (iPhone: app Calendario → calendario → Calendario público; Outlook: Configuración → Calendarios compartidos → Publicar).",
        "en": "Tap 🗓️ Subscribe and accept: your Juani appointments will show up in your calendar.\n\nOptional: to warn you about clashes with your calendar, paste its secret iCal link here (iPhone: Calendar app → calendar → Public Calendar; Outlook: Settings → Shared calendars → Publish).",
        "zh": "点击 🗓️ 订阅 并确认：你在 Juani 的安排会出现在日历里。\n\n可选：如需提醒与日历中的安排冲突，请把日历的私密 iCal 链接粘贴到这里（iPhone：日历 App → 日历 → 公开日历；Outlook：设置 → 共享日历 → 发布）。",
    },
    "cal_subscribe": {
        "es": "🗓️ Suscribirme",
        "en": "🗓️ Subscribe",
        "zh": "🗓️ 订阅",
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
        "es": "Hola, soy Juani 🫶 Tu asistente de gastos y agenda.\n\n🪙 Escribe -12 almuerzo y lo registro al instante.\n🧭 Mira tu mes en el Visor de gastos.\n🗓️ Agenda y recordatorios en lenguaje natural.\n🌎 Hablo español, inglés, chino, francés, alemán y portugués.\n\nSolo por invitación.",
        "en": "Hi, I'm Juani 🫶 Your expense and calendar assistant.\n\n🪙 Write -12 lunch and I log it right away.\n🧭 See your month in the Expense viewer.\n🗓️ Calendar and reminders in plain language.\n🌎 I speak English, Spanish, Chinese, French, German and Portuguese.\n\nInvitation only.",
        "zh": "你好，我是 Juani 🫶 你的记账和日程助手。\n\n🪙 发送 -12 午饭，我马上记下。\n🧭 在支出查看器里查看本月账单。\n🗓️ 用自然语言管理日程和提醒。\n🌎 我会说中文、英语、西班牙语、法语、德语和葡萄牙语。\n\n仅限邀请使用。",
    },
    "bot_about": {
        "es": "Juani: tus gastos, ingresos y agenda por chat. Escribe -12 almuerzo y listo 🧭",
        "en": "Juani: your expenses, income and calendar by chat. Write -12 lunch and done 🧭",
        "zh": "Juani：用聊天记录支出、收入和日程。发送 -12 午饭 即可 🧭",
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
        "es": "Activa o apaga las respuestas con imágenes",
        "en": "Turn image replies on or off",
        "zh": "开启或关闭图片回复",
    },
    "cmd_moneda": {
        "es": "La moneda en que ves tus montos",
        "en": "The currency your amounts show in",
        "zh": "显示金额所用的货币",
    },
    "cmd_reset": {
        "es": "Borra todos tus datos y el chat",
        "en": "Erase all your data and the chat",
        "zh": "清除你的全部数据和聊天",
    },
    "cmd_ayuda": {
        "es": "Cómo usar a Juani",
        "en": "How to use Juani",
        "zh": "如何使用 Juani",
    },
    # Web dashboard
    "months": {
        "es": "enero febrero marzo abril mayo junio julio agosto septiembre "
        "octubre noviembre diciembre",
        "en": "January February March April May June July August September "
        "October November December",
        "zh": "1月 2月 3月 4月 5月 6月 7月 8月 9月 10月 11月 12月",
    },
    "d_title": {
        "es": "Tablero de {month}",
        "en": "Dashboard · {month}",
        "zh": "{month} 账单",
    },
    "d_amounts_in": {
        "es": "Montos en {currency}.",
        "en": "Amounts in {currency}.",
        "zh": "金额单位：{currency}。",
    },
    "d_prev": {"es": "← Anterior", "en": "← Previous", "zh": "← 上个月"},
    "d_next": {"es": "Siguiente →", "en": "Next →", "zh": "下个月 →"},
    "d_income": {"es": "Ingresos", "en": "Income", "zh": "收入"},
    "d_expenses": {"es": "Gastos", "en": "Expenses", "zh": "支出"},
    "d_savings": {"es": "Ahorro", "en": "Savings", "zh": "结余"},
    "d_rate": {"es": "Tasa de ahorro", "en": "Savings rate", "zh": "储蓄率"},
    "d_goal": {
        "es": "Meta 20%: {goal} {currency}",
        "en": "20% goal: {goal} {currency}",
        "zh": "20% 目标：{goal} {currency}",
    },
    "d_no_income": {
        "es": "Sin ingresos este mes",
        "en": "No income this month",
        "zh": "本月没有收入",
    },
    "d_by_category": {
        "es": "Gastos por categoría",
        "en": "Expenses by category",
        "zh": "按类别支出",
    },
    "d_no_expenses": {"es": "Sin gastos.", "en": "No expenses.", "zh": "没有支出。"},
    "d_daily": {"es": "Gasto diario", "en": "Daily spending", "zh": "每日支出"},
    "d_latest": {
        "es": "Últimos {n} movimientos",
        "en": "Last {n} entries",
        "zh": "最近 {n} 笔记录",
    },
    "d_no_entries": {
        "es": "Sin movimientos.",
        "en": "No entries.",
        "zh": "没有记录。",
    },
}


# Stored category and 50/30/20 bucket keys (always Spanish) as shown to the user.
CATEGORY_NAMES: dict[str, dict[str, str]] = {
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


# --- French, German and Portuguese -----------------------------------------------------------

FR: dict[str, str] = {
    "welcome": """Salut 🫶 Je suis Juani, ton assistante sur ton téléphone. Je suis tes dépenses, tes revenus et ton agenda. Écris-moi simplement :

🪙 -12 déjeuner · 25000 cop courses · +1500 salaire (le + est un revenu)
🧹 /anular 1 supprime le dernier ; puis réécris-le
🧭 dashboard : ton mois · summary : aujourd'hui, semaine et mois
🗓️ réunion avec Ana demain 15h · calendar : ton agenda
📸 une photo de ton assiette (calories) ou d'un ticket avec « dîner 4 » (je partage l'addition) · splits : qui te doit
🪅 fun : je réponds avec des images

Écris juste le mot, sans « / ». help affiche ce message à nouveau.""",
    "guide": "🗺️ Guide complet",
    "viewer": "Visionneuse de dépenses",
    "dashboard": "Consulte ton tableau de bord ici 🫳",
    "hint": "Pour plus de détails, consulte ton tableau de bord : Visionneuse de dépenses 🧭",
    "spent_today": "Tes dépenses aujourd'hui : {total} {currency}.",
    "no_spending": "Tu n'as enregistré aucune dépense aujourd'hui.",
    "yesterday": "Hier : {total} {currency}.",
    "week": "Semaine {since}–{until} : {total} {currency}",
    "top": "Top : ",
    "no_income": "Aucun revenu ce mois-ci : enregistre-en un (+1000 salaire).",
    "month": "Mois : revenus {income}, dépenses {expenses} {currency}.",
    "save": "Épargne {savings} (20 %). Il te reste {left} {currency} ce mois-ci (~{week}/semaine).",
    "overspent": "Tu as dépassé de {excess} {currency} : ton épargne de {savings} est en danger.",
    "access_sent": "J'ai demandé l'accès au propriétaire de Juani. Je te préviens ici dès qu'il répond.",
    "access_wait": "Ta demande a été refusée. Tu pourras redemander {days} jours après le refus.",
    "access_today": "Je ne prends plus de demandes aujourd'hui. Réessaie demain avec /start.",
    "access_full": "Juani n'a plus de place pour de nouveaux utilisateurs pour le moment.",
    "access_granted": "✅ Tu as accès maintenant. Touche /start pour commencer.",
    "access_rejected": "Ta demande d'accès a été refusée. Tu pourras redemander dans {days} jours avec /start.",
    "inactive_warning": "Tu n'as pas utilisé Juani depuis un moment. Dans {days} jours, j'efface tes données et ton accès. Écris-moi n'importe quoi pour les garder.",
    "cal_status_google": "✅ Google Agenda connecté (synchronisé toutes les heures).",
    "cal_status_import": "✅ Agenda importé par lien iCal : je vois tes créneaux occupés.",
    "cal_status_feed_ok": "✅ Abonnement iPhone/Outlook actif : ton agenda l'a lu il y a {minutes} min.",
    "cal_status_feed_wait": "⏳ Lien d'abonnement créé, mais ton agenda ne l'a pas encore lu. Cela peut prendre quelques minutes.",
    "cal_status_none": "Aucun agenda connecté. Utilise calendario pour en connecter un.",
    "currency_button": "💱 Choisir la devise",
    "save_button": "Enregistrer",
    "currency_saved": "✓ Devise : {currency}. Ton heure : {time} ({zone}).",
    "edited_hint": "✏️ Je ne lis pas les messages modifiés. Pour corriger : /anular 1 (le dernier) puis réécris-le.",
    "weekly_off_button": "🔕 Ne plus envoyer ce résumé",
    "weekly_off": "🔕 C'est noté, plus de résumé le dimanche. weekly le réactive.",
    "weekly_on": "🔔 C'est noté, je t'envoie ton résumé de dépenses chaque dimanche à 18:00.",
    "limit": "Tu as atteint la limite pour le moment. Réessaie plus tard.",
    "text_only": "Pour l'instant je comprends le texte et les photos.",
    "failed": "Je n'ai pas pu le faire, réessaie.",
    "tz_usage": "Usage : /zona <zone IANA>, ex. /zona Europe/Paris. Actuelle : {tz}.",
    "tz_ok": "✓ Fuseau horaire : {tz}.",
    "void_usage": "Usage : /anular <n>, ex. /anular 1",
    "unavailable": "Pas encore disponible.",
    "link_not_configured": "Lien non configuré.",
    "dashboard_not_configured": "Tableau de bord non configuré.",
    "cancelled": "Annulé.",
    "photo_unavailable": "Je n'ai pas pu lire la photo pour le moment. Réessaie dans un instant.",
    "photo_other": "Envoie-moi la photo d'un repas (je compte les calories) ou d'un ticket avec le nombre de personnes, ex. « dîner 4 » (je partage l'addition).",
    "meal": "🍽️ {name} · ~{kcal} kcal\nProtéines {protein} g · Glucides {carbs} g · Lipides {fat} g\nAujourd'hui : ~{today} kcal.\n🕐 {times}",
    "meal_remove": "🗑️ Supprimer",
    "meal_removed": "C'est fait, supprimé.",
    "split_people": "🧾 {title} : {total} {currency}. Vous êtes combien à partager (toi compris) ?",
    "split": "🧾 {title} : {total} {currency} partagé en {people}\n{shares}\nTouche ✅ quand on te rembourse. splits montre ce qui reste.",
    "split_settled": "🎉 {title} : tout le monde t'a remboursé.",
    "split_pending": "On te doit :",
    "split_none": "Personne ne te doit rien. 🙌",
    "reset_question": "Tout effacer ? Tes dépenses, revenus, agenda, rappels, calendrier connecté, réglages et conversation seront supprimés. C'est irréversible.",
    "reset_yes": "🧨 Oui, tout effacer",
    "reset_no": "Annuler",
    "reset_done": "✓ C'est fait, nouveau départ. Telegram me laisse supprimer seulement les messages des dernières 48 h ; pour les plus anciens, utilise Effacer l'historique dans le chat.",
    "currency_first": "Avant d'enregistrer, choisis ta devise pour que tes montants soient justes.",
    "currency_question": "Dans quelle devise veux-tu voir tes montants ? Change-la plus tard avec currency.",
    "currency_ok": "✓ Devise : {currency}. Tes montants s'affichent en {currency}.",
    "fun_on": "🪅 Mode fun activé : je réponds avec des images et des GIF. /fun le désactive.",
    "fun_off": "Mode fun désactivé : je réponds avec l'enregistrement.",
    "positive": "Le montant doit être supérieur à 0.",
    "not_found": "Je n'ai pas trouvé cet enregistrement.",
    "currency_unsupported": "Devise non prise en charge.",
    "no_rate": "Je n'ai pas pu obtenir le taux {cur}, réessaie plus tard.",
    "voided": "✓ annulé : {entry}",
    "nothing_to_undo": "Rien à annuler.",
    "batch_not_found": "Lot introuvable.",
    "undone": "↩ annulé : {n} ligne(s)",
    "already_undone": "Ce lot a déjà été annulé.",
    "no_entries": "Aucun enregistrement.",
    "within_budget": "Dans le budget.",
    "over_budget": "Dépassement en {cat}{rule} : {spent} sur {cap} {currency} (+{extra}). Réduis d'abord là.",
    "no_budget": "Aucun budget ni revenu ce mois-ci pour comparer.",
    "empty_7_days": "Rien dans les 7 prochains jours.",
    "weekdays": "Lun Mar Mer Jeu Ven Sam Dim",
    "no_events": "Aucun événement.",
    "no_free_slots": "Aucun créneau libre.",
    "event_not_found": "Événement introuvable.",
    "event_cancelled": "✓ événement annulé",
    "invalid_link": "Lien invalide.",
    "cal_unreadable": "Je n'ai pas pu lire ce calendrier.",
    "cal_disconnected": "Calendrier déconnecté.",
    "cal_connected": "✓ Calendrier connecté.",
    "gcal_linked": "✓ Google Agenda connecté ({n} événements copiés). Tes nouveaux rendez-vous y apparaîtront et je te préviendrai des conflits avec Google.",
    "cal_connect": "🪢 Connecter le calendrier",
    "cal_disconnect": "✂️ Déconnecter {which}",
    "cal_choose": "Quel calendrier utilises-tu ?",
    "cal_google": "Touche le bouton, choisis ton compte et autorise l'accès à ton calendrier. Le lien est valable 10 minutes.",
    "cal_google_button": "Se connecter avec Google",
    "cal_ical": "Touche 🗓️ S'abonner et accepte : tes rendez-vous Juani apparaîtront dans ton calendrier.\n\nFacultatif : pour te prévenir des conflits avec ton calendrier, colle ici son lien iCal secret (iPhone : app Calendrier → calendrier → Calendrier public ; Outlook : Paramètres → Calendriers partagés → Publier).",
    "cal_subscribe": "🗓️ S'abonner",
    "oauth_ok": "✓ C'est fait, retourne sur Telegram.",
    "oauth_error": "Connexion impossible. Retourne sur Telegram et réessaie avec calendar.",
    "bot_description": "Salut, je suis Juani 🫶 Ton assistante de dépenses et d'agenda.\n\n🪙 Écris -12 déjeuner et je l'enregistre tout de suite.\n🧭 Vois ton mois dans la Visionneuse de dépenses.\n🗓️ Agenda et rappels en langage naturel.\n🌎 Je parle français, anglais, espagnol, chinois, allemand et portugais.\n\nSur invitation uniquement.",
    "bot_about": "Juani : tes dépenses, revenus et agenda par chat. Écris -12 déjeuner et c'est fait 🧭",
    "cmd_tablero": "Ta Visionneuse de dépenses du mois (dashboard pin l'épingle)",
    "cmd_resumen": "Tes dépenses d'aujourd'hui, de la semaine et du mois",
    "cmd_ultimos": "Tes 5 derniers enregistrements",
    "cmd_anular": "Annuler un enregistrement : /anular 1",
    "cmd_calendario": "Tes 7 prochains jours et la connexion de ton calendrier",
    "cmd_fun": "Activer ou désactiver les réponses en images",
    "cmd_moneda": "La devise de tes montants",
    "cmd_reset": "Effacer toutes tes données et le chat",
    "cmd_ayuda": "Comment utiliser Juani",
    "months": "janvier février mars avril mai juin juillet août septembre "
    "octobre novembre décembre",
    "d_title": "Tableau de bord · {month}",
    "d_amounts_in": "Montants en {currency}.",
    "d_prev": "← Précédent",
    "d_next": "Suivant →",
    "d_income": "Revenus",
    "d_expenses": "Dépenses",
    "d_savings": "Épargne",
    "d_rate": "Taux d'épargne",
    "d_goal": "Objectif 20 % : {goal} {currency}",
    "d_no_income": "Aucun revenu ce mois-ci",
    "d_by_category": "Dépenses par catégorie",
    "d_no_expenses": "Aucune dépense.",
    "d_daily": "Dépenses par jour",
    "d_latest": "{n} derniers enregistrements",
    "d_no_entries": "Aucun enregistrement.",
}

DE: dict[str, str] = {
    "welcome": """Hallo 🫶 Ich bin Juani, deine Assistentin auf deinem Handy. Ich verfolge deine Ausgaben, Einnahmen und Termine. Schreib mir einfach:

🪙 -12 Mittagessen · 25000 cop Einkauf · +1500 Gehalt (+ heißt Einnahme)
🧹 /anular 1 löscht den letzten Eintrag; dann schreib ihn neu
🧭 dashboard: dein Monat · summary: heute, Woche und Monat
🗓️ Treffen mit Ana morgen 15 Uhr · calendar: deine Termine
📸 ein Foto deines Essens (Kalorien) oder einer Rechnung mit „Abendessen 4“ (ich teile sie auf) · splits: wer dir etwas schuldet
🪅 fun: ich antworte mit Bildern

Schreib nur das Wort, ohne „/“. help zeigt das hier erneut.""",
    "guide": "🗺️ Vollständige Anleitung",
    "viewer": "Ausgabenübersicht",
    "dashboard": "Hier ist dein Dashboard 🫳",
    "hint": "Mehr Details in deinem Dashboard: Ausgabenübersicht 🧭",
    "spent_today": "Deine Ausgaben heute: {total} {currency}.",
    "no_spending": "Du hast heute keine Ausgaben eingetragen.",
    "yesterday": "Gestern: {total} {currency}.",
    "week": "Woche {since}–{until}: {total} {currency}",
    "top": "Top: ",
    "no_income": "Keine Einnahmen diesen Monat: trag eine ein (+1000 Gehalt).",
    "month": "Monat: Einnahmen {income}, Ausgaben {expenses} {currency}.",
    "save": "Spare {savings} (20 %). Dir bleiben diesen Monat {left} {currency} (~{week}/Woche).",
    "overspent": "Du liegst {excess} {currency} drüber: deine {savings} Ersparnis ist in Gefahr.",
    "access_sent": "Ich habe Juanis Besitzer um Zugang gebeten. Ich sage dir hier Bescheid, sobald eine Antwort kommt.",
    "access_wait": "Deine Anfrage wurde abgelehnt. Du kannst {days} Tage nach der Ablehnung erneut fragen.",
    "access_today": "Heute nehme ich keine Anfragen mehr an. Versuch es morgen mit /start.",
    "access_full": "Juani hat im Moment keinen Platz für weitere Nutzer.",
    "access_granted": "✅ Du hast jetzt Zugang. Tippe auf /start, um loszulegen.",
    "access_rejected": "Deine Zugangsanfrage wurde abgelehnt. Du kannst in {days} Tagen mit /start erneut fragen.",
    "inactive_warning": "Du hast Juani eine Weile nicht benutzt. In {days} Tagen lösche ich deine Daten und deinen Zugang. Schreib mir irgendwas, um sie zu behalten.",
    "cal_status_google": "✅ Google Kalender verbunden (synchronisiert stündlich).",
    "cal_status_import": "✅ Kalender per iCal-Link importiert: Ich sehe deine belegten Zeiten.",
    "cal_status_feed_ok": "✅ iPhone/Outlook-Abo funktioniert: Dein Kalender hat es vor {minutes} Min. gelesen.",
    "cal_status_feed_wait": "⏳ Abo-Link erstellt, aber dein Kalender hat ihn noch nicht gelesen. Das kann nach dem Abonnieren ein paar Minuten dauern.",
    "cal_status_none": "Kein Kalender verbunden. Nutze calendario, um einen zu verbinden.",
    "currency_button": "💱 Währung wählen",
    "save_button": "Speichern",
    "currency_saved": "✓ Währung: {currency}. Deine Uhrzeit: {time} ({zone}).",
    "edited_hint": "✏️ Bearbeitete Nachrichten lese ich nicht. Zum Korrigieren: /anular 1 (der letzte) und neu schreiben.",
    "weekly_off_button": "🔕 Diese Übersicht nicht mehr senden",
    "weekly_off": "🔕 Erledigt, keine Sonntagsübersicht mehr. weekly schaltet sie wieder ein.",
    "weekly_on": "🔔 Erledigt, ich schicke dir jeden Sonntag um 18:00 deine Ausgabenübersicht.",
    "limit": "Du hast vorerst das Limit erreicht. Versuch es später noch einmal.",
    "text_only": "Im Moment verstehe ich Text und Fotos.",
    "failed": "Das hat nicht geklappt, bitte versuch es noch einmal.",
    "tz_usage": "Nutzung: /zona <IANA-Zone>, z. B. /zona Europe/Berlin. Aktuell: {tz}.",
    "tz_ok": "✓ Zeitzone: {tz}.",
    "void_usage": "Nutzung: /anular <n>, z. B. /anular 1",
    "unavailable": "Noch nicht verfügbar.",
    "link_not_configured": "Link nicht eingerichtet.",
    "dashboard_not_configured": "Dashboard nicht eingerichtet.",
    "cancelled": "Abgebrochen.",
    "photo_unavailable": "Ich konnte das Foto gerade nicht lesen. Versuch es gleich noch einmal.",
    "photo_other": "Schick mir ein Foto einer Mahlzeit (ich zähle Kalorien) oder einer Rechnung mit der Personenzahl, z. B. „Abendessen 4“ (ich teile die Rechnung auf).",
    "meal": "🍽️ {name} · ~{kcal} kcal\nEiweiß {protein} g · Kohlenhydrate {carbs} g · Fett {fat} g\nHeute bisher: ~{today} kcal.\n🕐 {times}",
    "meal_remove": "🗑️ Entfernen",
    "meal_removed": "Erledigt, entfernt.",
    "split_people": "🧾 {title}: {total} {currency}. Durch wie viele Personen teilen (dich eingeschlossen)?",
    "split": "🧾 {title}: {total} {currency} geteilt durch {people}\n{shares}\nTippe ✅, wenn sie dich bezahlen. splits zeigt, was noch offen ist.",
    "split_settled": "🎉 {title}: alle haben dich bezahlt.",
    "split_pending": "Man schuldet dir:",
    "split_none": "Niemand schuldet dir etwas. 🙌",
    "reset_question": "Alles löschen? Deine Ausgaben, Einnahmen, Termine, Erinnerungen, der verbundene Kalender, Einstellungen und der Chatverlauf werden gelöscht. Das kann nicht rückgängig gemacht werden.",
    "reset_yes": "🧨 Ja, alles löschen",
    "reset_no": "Abbrechen",
    "reset_done": "✓ Erledigt, ein Neuanfang. Telegram lässt mich nur Nachrichten der letzten 48 Std. löschen; für ältere nutze Verlauf leeren im Chat.",
    "currency_first": "Bevor du etwas einträgst, wähle deine Währung, damit deine Beträge stimmen.",
    "currency_question": "In welcher Währung willst du deine Beträge sehen? Ändere sie später mit currency.",
    "currency_ok": "✓ Währung: {currency}. Deine Beträge erscheinen in {currency}.",
    "fun_on": "🪅 Fun-Modus an: ich antworte mit Bildern und GIFs. /fun schaltet ihn aus.",
    "fun_off": "Fun-Modus aus: ich antworte mit dem Eintrag.",
    "positive": "Der Betrag muss größer als 0 sein.",
    "not_found": "Ich konnte diesen Eintrag nicht finden.",
    "currency_unsupported": "Währung nicht unterstützt.",
    "no_rate": "Ich konnte den Kurs für {cur} nicht abrufen, versuch es später.",
    "voided": "✓ storniert: {entry}",
    "nothing_to_undo": "Nichts rückgängig zu machen.",
    "batch_not_found": "Stapel nicht gefunden.",
    "undone": "↩ rückgängig: {n} Zeile(n)",
    "already_undone": "Dieser Stapel wurde schon rückgängig gemacht.",
    "no_entries": "Keine Einträge.",
    "within_budget": "Im Budget.",
    "over_budget": "Drüber bei {cat}{rule}: {spent} von {cap} {currency} (+{extra}). Spar zuerst dort.",
    "no_budget": "Kein Budget und keine Einnahmen diesen Monat zum Vergleichen.",
    "empty_7_days": "Nichts in den nächsten 7 Tagen.",
    "weekdays": "Mo Di Mi Do Fr Sa So",
    "no_events": "Keine Termine.",
    "no_free_slots": "Keine freien Zeiten.",
    "event_not_found": "Termin nicht gefunden.",
    "event_cancelled": "✓ Termin abgesagt",
    "invalid_link": "Ungültiger Link.",
    "cal_unreadable": "Ich konnte diesen Kalender nicht lesen.",
    "cal_disconnected": "Kalender getrennt.",
    "cal_connected": "✓ Kalender verbunden.",
    "gcal_linked": "✓ Google Kalender verbunden ({n} Termine kopiert). Neue Termine erscheinen dort, und ich warne dich vor Überschneidungen mit Google.",
    "cal_connect": "🪢 Kalender verbinden",
    "cal_disconnect": "✂️ {which} trennen",
    "cal_choose": "Welchen Kalender nutzt du?",
    "cal_google": "Tippe auf den Button, wähle dein Konto und erlaube den Zugriff auf deinen Kalender. Der Link gilt 10 Minuten.",
    "cal_google_button": "Mit Google verbinden",
    "cal_ical": "Tippe auf 🗓️ Abonnieren und bestätige: deine Juani-Termine erscheinen in deinem Kalender.\n\nOptional: damit ich dich vor Überschneidungen warne, füge hier den geheimen iCal-Link deines Kalenders ein (iPhone: Kalender-App → Kalender → Öffentlicher Kalender; Outlook: Einstellungen → Freigegebene Kalender → Veröffentlichen).",
    "cal_subscribe": "🗓️ Abonnieren",
    "oauth_ok": "✓ Erledigt, geh zurück zu Telegram.",
    "oauth_error": "Verbindung fehlgeschlagen. Geh zurück zu Telegram und versuch es erneut mit calendar.",
    "bot_description": "Hallo, ich bin Juani 🫶 Deine Assistentin für Ausgaben und Termine.\n\n🪙 Schreib -12 Mittagessen und ich trage es sofort ein.\n🧭 Sieh deinen Monat in der Ausgabenübersicht.\n🗓️ Termine und Erinnerungen in natürlicher Sprache.\n🌎 Ich spreche Deutsch, Englisch, Spanisch, Chinesisch, Französisch und Portugiesisch.\n\nNur mit Einladung.",
    "bot_about": "Juani: deine Ausgaben, Einnahmen und Termine per Chat. Schreib -12 Mittagessen, fertig 🧭",
    "cmd_tablero": "Deine Ausgabenübersicht des Monats (dashboard pin heftet sie an)",
    "cmd_resumen": "Deine Ausgaben heute, diese Woche und diesen Monat",
    "cmd_ultimos": "Deine letzten 5 Einträge",
    "cmd_anular": "Einen Eintrag stornieren: /anular 1",
    "cmd_calendario": "Deine nächsten 7 Tage und Kalender verbinden",
    "cmd_fun": "Bild-Antworten an- oder ausschalten",
    "cmd_moneda": "Die Währung deiner Beträge",
    "cmd_reset": "Alle deine Daten und den Chat löschen",
    "cmd_ayuda": "So nutzt du Juani",
    "months": "Januar Februar März April Mai Juni Juli August September "
    "Oktober November Dezember",
    "d_title": "Dashboard · {month}",
    "d_amounts_in": "Beträge in {currency}.",
    "d_prev": "← Zurück",
    "d_next": "Weiter →",
    "d_income": "Einnahmen",
    "d_expenses": "Ausgaben",
    "d_savings": "Ersparnis",
    "d_rate": "Sparquote",
    "d_goal": "Ziel 20 %: {goal} {currency}",
    "d_no_income": "Keine Einnahmen diesen Monat",
    "d_by_category": "Ausgaben nach Kategorie",
    "d_no_expenses": "Keine Ausgaben.",
    "d_daily": "Ausgaben pro Tag",
    "d_latest": "Letzte {n} Einträge",
    "d_no_entries": "Keine Einträge.",
}

PT: dict[str, str] = {
    "welcome": """Oi 🫶 Sou a Juani, sua assistente no seu celular. Acompanho seus gastos, receitas e agenda. É só me escrever:

🪙 -12 almoço · 25000 cop mercado · +1500 salário (o + é receita)
🧹 /anular 1 remove o último; depois escreva de novo
🧭 dashboard: seu mês · summary: hoje, semana e mês
🗓️ reunião com Ana amanhã 15h · calendar: sua agenda
📸 foto do seu prato (calorias) ou de um recibo com «jantar 4» (eu divido a conta) · splits: quem te deve
🪅 fun: respondo com imagens

Escreva só a palavra, sem "/". help mostra isto de novo.""",
    "guide": "🗺️ Guia completo",
    "viewer": "Visor de gastos",
    "dashboard": "Veja seu painel aqui 🫳",
    "hint": "Para mais detalhes, veja seu painel: Visor de gastos 🧭",
    "spent_today": "Seus gastos hoje: {total} {currency}.",
    "no_spending": "Você não registrou gastos hoje.",
    "yesterday": "Ontem: {total} {currency}.",
    "week": "Semana {since}–{until}: {total} {currency}",
    "top": "Top: ",
    "no_income": "Sem receitas este mês: registre uma (+1000 salário).",
    "month": "Mês: receitas {income}, gastos {expenses} {currency}.",
    "save": "Poupe {savings} (20%). Restam {left} {currency} este mês (~{week}/semana).",
    "overspent": "Você passou {excess} {currency}: sua poupança de {savings} está em risco.",
    "access_sent": "Pedi acesso ao dono da Juani. Aviso aqui assim que ele responder.",
    "access_wait": "Seu pedido foi recusado. Você pode pedir de novo {days} dias após a recusa.",
    "access_today": "Não estou aceitando mais pedidos hoje. Tente amanhã com /start.",
    "access_full": "A Juani não tem vagas para novos usuários agora.",
    "access_granted": "✅ Agora você tem acesso. Toque em /start para começar.",
    "access_rejected": "Seu pedido de acesso foi recusado. Você pode pedir de novo em {days} dias com /start.",
    "inactive_warning": "Você não usa a Juani há um tempo. Em {days} dias, apago seus dados e seu acesso. Escreva qualquer coisa para mantê-los.",
    "cal_status_google": "✅ Google Agenda conectado (sincroniza a cada hora).",
    "cal_status_import": "✅ Agenda importada por link iCal: vejo seus horários ocupados.",
    "cal_status_feed_ok": "✅ Assinatura iPhone/Outlook ativa: sua agenda leu há {minutes} min.",
    "cal_status_feed_wait": "⏳ Link de assinatura criado, mas sua agenda ainda não leu. Pode levar alguns minutos.",
    "cal_status_none": "Nenhuma agenda conectada. Use calendario para conectar uma.",
    "currency_button": "💱 Escolher moeda",
    "save_button": "Salvar",
    "currency_saved": "✓ Moeda: {currency}. Sua hora: {time} ({zone}).",
    "edited_hint": "✏️ Não leio mensagens editadas. Para corrigir: /anular 1 (o último) e escreva de novo.",
    "weekly_off_button": "🔕 Não enviar este resumo",
    "weekly_off": "🔕 Pronto, sem resumo aos domingos. weekly ativa de novo.",
    "weekly_on": "🔔 Pronto, envio seu resumo de gastos todo domingo às 18:00.",
    "limit": "Você atingiu o limite por agora. Tente mais tarde.",
    "text_only": "Por enquanto entendo texto e fotos.",
    "failed": "Não consegui, tente de novo.",
    "tz_usage": "Uso: /zona <zona IANA>, ex. /zona America/Sao_Paulo. Atual: {tz}.",
    "tz_ok": "✓ Fuso horário: {tz}.",
    "void_usage": "Uso: /anular <n>, ex. /anular 1",
    "unavailable": "Ainda não disponível.",
    "link_not_configured": "Link não configurado.",
    "dashboard_not_configured": "Painel não configurado.",
    "cancelled": "Cancelado.",
    "photo_unavailable": "Não consegui ler a foto agora. Tente de novo em instantes.",
    "photo_other": "Mande a foto de um prato (conto as calorias) ou de um recibo com quantas pessoas, ex. «jantar 4» (eu divido a conta).",
    "meal": "🍽️ {name} · ~{kcal} kcal\nProteína {protein} g · Carboidratos {carbs} g · Gordura {fat} g\nHoje você está em ~{today} kcal.\n🕐 {times}",
    "meal_remove": "🗑️ Remover",
    "meal_removed": "Pronto, removido.",
    "split_people": "🧾 {title}: {total} {currency}. Entre quantas pessoas dividir (com você)?",
    "split": "🧾 {title}: {total} {currency} dividido entre {people}\n{shares}\nToque ✅ quando te pagarem. splits mostra o que falta.",
    "split_settled": "🎉 {title}: todo mundo te pagou.",
    "split_pending": "Te devem:",
    "split_none": "Ninguém te deve nada. 🙌",
    "reset_question": "Apagar tudo? Seus gastos, receitas, agenda, lembretes, agenda conectada, ajustes e conversa serão apagados. Não dá para desfazer.",
    "reset_yes": "🧨 Sim, apagar tudo",
    "reset_no": "Cancelar",
    "reset_done": "✓ Pronto, começamos do zero. O Telegram só me deixa apagar mensagens das últimas 48 h; para as mais antigas use Limpar histórico no chat.",
    "currency_first": "Antes de registrar, escolha sua moeda para que seus valores fiquem certos.",
    "currency_question": "Em que moeda você quer ver seus valores? Mude depois com currency.",
    "currency_ok": "✓ Moeda: {currency}. Seus valores aparecem em {currency}.",
    "fun_on": "🪅 Modo fun ativado: respondo com imagens e GIFs. /fun desativa.",
    "fun_off": "Modo fun desativado: respondo com o registro.",
    "positive": "O valor deve ser maior que 0.",
    "not_found": "Não encontrei esse registro.",
    "currency_unsupported": "Moeda não suportada.",
    "no_rate": "Não consegui a cotação de {cur}, tente mais tarde.",
    "voided": "✓ anulado: {entry}",
    "nothing_to_undo": "Nada para desfazer.",
    "batch_not_found": "Lote não encontrado.",
    "undone": "↩ desfeito: {n} linha(s)",
    "already_undone": "Esse lote já foi desfeito.",
    "no_entries": "Sem registros.",
    "within_budget": "Dentro do orçamento.",
    "over_budget": "Acima em {cat}{rule}: {spent} de {cap} {currency} (+{extra}). Corte primeiro aí.",
    "no_budget": "Sem orçamento nem receitas este mês para comparar.",
    "empty_7_days": "Nada nos próximos 7 dias.",
    "weekdays": "Seg Ter Qua Qui Sex Sáb Dom",
    "no_events": "Sem eventos.",
    "no_free_slots": "Sem horários livres.",
    "event_not_found": "Evento não encontrado.",
    "event_cancelled": "✓ evento cancelado",
    "invalid_link": "Link inválido.",
    "cal_unreadable": "Não consegui ler essa agenda.",
    "cal_disconnected": "Agenda desconectada.",
    "cal_connected": "✓ Agenda conectada.",
    "gcal_linked": "✓ Google Agenda conectado ({n} eventos copiados). Seus novos compromissos vão aparecer lá e aviso sobre conflitos com o Google.",
    "cal_connect": "🪢 Conectar agenda",
    "cal_disconnect": "✂️ Desconectar {which}",
    "cal_choose": "Qual agenda você usa?",
    "cal_google": "Toque no botão, escolha sua conta e permita o acesso à sua agenda. O link vale 10 minutos.",
    "cal_google_button": "Entrar com Google",
    "cal_ical": "Toque em 🗓️ Assinar e aceite: seus compromissos da Juani vão aparecer na sua agenda.\n\nOpcional: para avisar sobre conflitos com sua agenda, cole aqui o link iCal secreto dela (iPhone: app Calendário → calendário → Calendário público; Outlook: Configurações → Calendários compartilhados → Publicar).",
    "cal_subscribe": "🗓️ Assinar",
    "oauth_ok": "✓ Pronto, volte ao Telegram.",
    "oauth_error": "Não consegui conectar. Volte ao Telegram e tente de novo com calendar.",
    "bot_description": "Oi, sou a Juani 🫶 Sua assistente de gastos e agenda.\n\n🪙 Escreva -12 almoço e registro na hora.\n🧭 Veja seu mês no Visor de gastos.\n🗓️ Agenda e lembretes em linguagem natural.\n🌎 Falo português, espanhol, inglês, chinês, francês e alemão.\n\nSó por convite.",
    "bot_about": "Juani: seus gastos, receitas e agenda pelo chat. Escreva -12 almoço e pronto 🧭",
    "cmd_tablero": "Seu Visor de gastos do mês (dashboard pin fixa)",
    "cmd_resumen": "Seus gastos de hoje, da semana e do mês",
    "cmd_ultimos": "Seus últimos 5 registros",
    "cmd_anular": "Anular um registro: /anular 1",
    "cmd_calendario": "Seus próximos 7 dias e conectar sua agenda",
    "cmd_fun": "Ativar ou desativar respostas com imagens",
    "cmd_moneda": "A moeda dos seus valores",
    "cmd_reset": "Apagar todos os seus dados e o chat",
    "cmd_ayuda": "Como usar a Juani",
    "months": "janeiro fevereiro março abril maio junho julho agosto setembro "
    "outubro novembro dezembro",
    "d_title": "Painel · {month}",
    "d_amounts_in": "Valores em {currency}.",
    "d_prev": "← Anterior",
    "d_next": "Próximo →",
    "d_income": "Receitas",
    "d_expenses": "Gastos",
    "d_savings": "Poupança",
    "d_rate": "Taxa de poupança",
    "d_goal": "Meta 20%: {goal} {currency}",
    "d_no_income": "Sem receitas este mês",
    "d_by_category": "Gastos por categoria",
    "d_no_expenses": "Sem gastos.",
    "d_daily": "Gastos por dia",
    "d_latest": "Últimos {n} registros",
    "d_no_entries": "Sem registros.",
}

# Category names: (French, German, Portuguese).
_CATEGORIES_FR_DE_PT = {
    "vivienda": ("Logement", "Wohnen", "Moradia"),
    "servicios": ("Factures", "Nebenkosten", "Contas"),
    "supermercado": ("Courses", "Lebensmittel", "Mercado"),
    "transporte": ("Transport", "Verkehr", "Transporte"),
    "salud": ("Santé", "Gesundheit", "Saúde"),
    "deudas": ("Dettes", "Schulden", "Dívidas"),
    "restaurantes": ("Restaurants", "Restaurants", "Restaurantes"),
    "entretenimiento": ("Loisirs", "Unterhaltung", "Lazer"),
    "compras": ("Achats", "Shopping", "Compras"),
    "viajes": ("Voyages", "Reisen", "Viagens"),
    "suscripciones": ("Abonnements", "Abos", "Assinaturas"),
    "otros": ("Autres", "Sonstiges", "Outros"),
    "ahorro": ("Épargne", "Sparen", "Poupança"),
    "inversion": ("Investissement", "Investition", "Investimento"),
    "necesidades": ("Besoins", "Bedarf", "Necessidades"),
    "ocio": ("Envies", "Freizeit", "Desejos"),
}

for _lang, _texts in (("fr", FR), ("de", DE), ("pt", PT)):
    for _key, _text in _texts.items():
        TEXTS[_key][_lang] = _text
for _key, (_fr, _de, _pt) in _CATEGORIES_FR_DE_PT.items():
    CATEGORY_NAMES[_key] |= {"fr": _fr, "de": _de, "pt": _pt}

# --- meal plan (/plan): (es, en, zh, fr, de, pt), in LANGS order ------------------

_PLAN: dict[str, tuple[str, str, str, str, str, str]] = {
    "plan_offer": (
        "¿Quieres un plan de alimentación? Con tu meta, edad, peso y altura calculo cuántas calorías te tocan al día. Es opcional: también puedes hacerlo luego con /plan.",
        "Want a meal plan? With your goal, age, weight and height I estimate your daily calories. It's optional: you can also do it later with /plan.",
        "想要一个饮食计划吗？根据你的目标、年龄、体重和身高，我会估算你每天的热量。这是可选的：之后也可以用 /plan 设置。",
        "Tu veux un plan alimentaire ? Avec ton objectif, ton âge, ton poids et ta taille, j'estime tes calories du jour. C'est facultatif : tu peux aussi le faire plus tard avec /plan.",
        "Möchtest du einen Ernährungsplan? Mit Ziel, Alter, Gewicht und Größe schätze ich deine Kalorien pro Tag. Optional: du kannst es auch später mit /plan machen.",
        "Quer um plano alimentar? Com sua meta, idade, peso e altura eu estimo suas calorias do dia. É opcional: você também pode fazer depois com /plan.",
    ),
    "plan_button": (
        "🥗 Plan de alimentación",
        "🥗 Meal plan",
        "🥗 饮食计划",
        "🥗 Plan alimentaire",
        "🥗 Ernährungsplan",
        "🥗 Plano alimentar",
    ),
    "plan_question": (
        "Tu plan de alimentación",
        "Your meal plan",
        "你的饮食计划",
        "Ton plan alimentaire",
        "Dein Ernährungsplan",
        "Seu plano alimentar",
    ),
    "plan_current": (
        "🥗 Tu plan: {goal} · ~{kcal} kcal/día. Cámbialo aquí o bórralo con /plan borrar.",
        "🥗 Your plan: {goal} · ~{kcal} kcal/day. Change it here or delete it with /plan delete.",
        "🥗 你的计划：{goal} · 约 {kcal} 千卡/天。在这里修改，或用 /plan delete 删除。",
        "🥗 Ton plan : {goal} · ~{kcal} kcal/jour. Modifie-le ici ou supprime-le avec /plan delete.",
        "🥗 Dein Plan: {goal} · ~{kcal} kcal/Tag. Ändere ihn hier oder lösche ihn mit /plan delete.",
        "🥗 Seu plano: {goal} · ~{kcal} kcal/dia. Mude aqui ou apague com /plan delete.",
    ),
    "plan_saved": (
        "✓ Plan: {goal} · ~{kcal} kcal al día. Es una estimación, no un consejo médico.",
        "✓ Plan: {goal} · ~{kcal} kcal a day. It's an estimate, not medical advice.",
        "✓ 计划：{goal} · 每天约 {kcal} 千卡。这只是估算，不是医疗建议。",
        "✓ Plan : {goal} · ~{kcal} kcal par jour. C'est une estimation, pas un avis médical.",
        "✓ Plan: {goal} · ~{kcal} kcal am Tag. Eine Schätzung, kein ärztlicher Rat.",
        "✓ Plano: {goal} · ~{kcal} kcal por dia. É uma estimativa, não um conselho médico.",
    ),
    "plan_deleted": (
        "✓ Borré tu plan de alimentación y tus datos (edad, peso, altura).",
        "✓ I deleted your meal plan and its data (age, weight, height).",
        "✓ 已删除你的饮食计划及其数据（年龄、体重、身高）。",
        "✓ J'ai supprimé ton plan alimentaire et ses données (âge, poids, taille).",
        "✓ Ich habe deinen Ernährungsplan und seine Daten (Alter, Gewicht, Größe) gelöscht.",
        "✓ Apaguei seu plano alimentar e seus dados (idade, peso, altura).",
    ),
    "plan_goal": ("Meta", "Goal", "目标", "Objectif", "Ziel", "Meta"),
    "plan_sex": ("Sexo", "Sex", "性别", "Sexe", "Geschlecht", "Sexo"),
    "sex_m": ("Mujer", "Female", "女", "Femme", "Weiblich", "Mulher"),
    "sex_h": ("Hombre", "Male", "男", "Homme", "Männlich", "Homem"),
    "plan_age": (
        "Edad (años)",
        "Age (years)",
        "年龄（岁）",
        "Âge (ans)",
        "Alter (Jahre)",
        "Idade (anos)",
    ),
    "plan_weight": (
        "Peso (kg)",
        "Weight (kg)",
        "体重（公斤）",
        "Poids (kg)",
        "Gewicht (kg)",
        "Peso (kg)",
    ),
    "plan_height": (
        "Altura (cm)",
        "Height (cm)",
        "身高（厘米）",
        "Taille (cm)",
        "Größe (cm)",
        "Altura (cm)",
    ),
    "plan_activity": (
        "Actividad",
        "Activity",
        "活动量",
        "Activité",
        "Aktivität",
        "Atividade",
    ),
    "act_baja": (
        "Baja: casi todo el día sentado",
        "Low: sitting most of the day",
        "低：大部分时间坐着",
        "Faible : assis presque toute la journée",
        "Niedrig: fast den ganzen Tag sitzend",
        "Baixa: sentado quase o dia todo",
    ),
    "act_media": (
        "Media: ejercicio 1-3 días por semana",
        "Medium: exercise 1-3 days a week",
        "中：每周运动 1-3 天",
        "Moyenne : sport 1-3 jours par semaine",
        "Mittel: Sport an 1-3 Tagen pro Woche",
        "Média: exercício 1-3 dias por semana",
    ),
    "act_alta": (
        "Alta: ejercicio 4 o más días por semana",
        "High: exercise 4 or more days a week",
        "高：每周运动 4 天以上",
        "Élevée : sport 4 jours ou plus par semaine",
        "Hoch: Sport an 4 oder mehr Tagen pro Woche",
        "Alta: exercício 4 ou mais dias por semana",
    ),
    "goal_bajar": (
        "bajar de peso",
        "lose weight",
        "减重",
        "perdre du poids",
        "abnehmen",
        "perder peso",
    ),
    "goal_mantener": (
        "mantener mi peso",
        "keep my weight",
        "保持体重",
        "garder mon poids",
        "Gewicht halten",
        "manter meu peso",
    ),
    "goal_subir": (
        "subir de peso",
        "gain weight",
        "增重",
        "prendre du poids",
        "zunehmen",
        "ganhar peso",
    ),
    "goal_sano": (
        "comer más sano",
        "eat healthier",
        "吃得更健康",
        "manger plus sain",
        "gesünder essen",
        "comer mais saudável",
    ),
    "plan_privacy": (
        "Opcional. Solo se usa para estimar tus calorías; la meta y las calorías ayudan a los consejos, nunca tu edad, peso o altura. Bórralo con /plan borrar o /reset. Es una estimación, no un consejo médico.",
        "Optional. Used only to estimate your calories; the goal and calories guide the tips, never your age, weight or height. Delete it with /plan delete or /reset. An estimate, not medical advice.",
        "可选。仅用于估算你的热量；建议只参考目标和热量，从不使用你的年龄、体重或身高。用 /plan delete 或 /reset 删除。仅为估算，不是医疗建议。",
        "Facultatif. Sert seulement à estimer tes calories ; l'objectif et les calories guident les conseils, jamais ton âge, poids ou taille. Supprime-le avec /plan delete ou /reset. Une estimation, pas un avis médical.",
        "Optional. Nur zur Schätzung deiner Kalorien; Ziel und Kalorien leiten die Tipps, nie Alter, Gewicht oder Größe. Löschen mit /plan delete oder /reset. Eine Schätzung, kein ärztlicher Rat.",
        "Opcional. Só serve para estimar suas calorias; a meta e as calorias guiam as dicas, nunca sua idade, peso ou altura. Apague com /plan delete ou /reset. Uma estimativa, não um conselho médico.",
    ),
    "meal_left": (
        "🎯 Te quedan ~{left} de {target} kcal hoy.",
        "🎯 ~{left} of {target} kcal left today.",
        "🎯 今天还剩约 {left} / {target} 千卡。",
        "🎯 Il te reste ~{left} sur {target} kcal aujourd'hui.",
        "🎯 Heute noch ~{left} von {target} kcal übrig.",
        "🎯 Restam ~{left} de {target} kcal hoje.",
    ),
    "meal_over": (
        "🎯 Vas ~{over} kcal por encima de tu meta de {target}.",
        "🎯 ~{over} kcal over your {target} target.",
        "🎯 已超出 {target} 千卡目标约 {over} 千卡。",
        "🎯 ~{over} kcal au-dessus de ton objectif de {target}.",
        "🎯 ~{over} kcal über deinem Ziel von {target}.",
        "🎯 ~{over} kcal acima da sua meta de {target}.",
    ),
    "meal_no_plan": (
        "🎯 Define tu meta con /plan y te digo cuánto te queda cada día.",
        "🎯 Set your goal with /plan and I'll tell you what's left each day.",
        "🎯 用 /plan 设定目标，我会告诉你每天还剩多少。",
        "🎯 Fixe ton objectif avec /plan et je te dis ce qu'il reste chaque jour.",
        "🎯 Setz dein Ziel mit /plan und ich sage dir, was jeden Tag übrig ist.",
        "🎯 Defina sua meta com /plan e eu digo quanto resta a cada dia.",
    ),
    "cmd_plan": (
        "Tu plan de alimentación y meta de calorías",
        "Your meal plan and calorie goal",
        "你的饮食计划和热量目标",
        "Ton plan alimentaire et ton objectif de calories",
        "Dein Ernährungsplan und Kalorienziel",
        "Seu plano alimentar e meta de calorias",
    ),
}
for _key, _row in _PLAN.items():
    TEXTS[_key] = dict(zip(LANGS, _row, strict=True))


def category_name(lang: str, key: str) -> str | None:
    """A stored category key in ``lang``; None for free text (a note)."""
    names = CATEGORY_NAMES.get(key)
    return names.get(lang, names["en"]) if names else None


def t(lang: str, key: str, **values: object) -> str:
    texts = TEXTS[key]
    return texts.get(lang, texts["en"]).format(**values)

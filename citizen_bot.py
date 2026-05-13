import httpx
import json
import re
import logging
from datetime import datetime, timedelta, date as _date
from pathlib import Path
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI()

# ---------------------------------------------------------------------------
# 1. CONFIGURATION  -- fill these before running
# ---------------------------------------------------------------------------
ACCESS_TOKEN    = "EAAVYo9qkDuQBRScqbPdHV3qgZBtUUJZB8wnnyfpUdY1FJICnnuJWzcAdI7UNjsn4wbtyBWpZCx6y07j6u0lCs9YaDRyOEmNrbUibJIT4LYTVp3hbnoNNGYRdV1Gp3p2zfFfulGMZASHV13o2dKWWOvnPfY2vIIgiNAhYsQOSYOKyCY3N4umG1WxDIwMw1tBnYKZCUltqZBZAIEZAvB3LyQJedjnkq7wkZCq3qJeQU82ZCzm7LnZBapo8QdAN5O6qN9nk9jjTGUxGcpI0RdYmXZBlfzW5rTGS"
PHONE_NUMBER_ID = "1003362262871598"
VERIFY_TOKEN    = "my_cafe_bot"
BUSINESS_EMAIL  = "designs@citizenprint.com"

# ---------------------------------------------------------------------------
# 2. LOAD flow.json
# ---------------------------------------------------------------------------
FLOW_PATH = Path(__file__).parent / "flow.json"

def load_flow() -> dict:
    with open(FLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

FLOW             = load_flow()
STATES           = FLOW["states"]
PRODUCTS         = FLOW["products"]
PRODUCT_KEYWORDS = FLOW["product_keywords"]

# States whose keywords always work even mid-flow
ESCAPE_STATES   = {"WELCOME", "CATALOG", "HOURS", "SUNDAY_HOLIDAY", "ORDER", "PRODUCT_INFO"}
# States that are actively waiting for a specific customer reply
MID_FLOW_STATES = {"AWAITING_PRODUCT", "AWAITING_DATE"}

# ---------------------------------------------------------------------------
# 3. SESSION STORE
# ---------------------------------------------------------------------------
sessions: dict = {}

def get_session(sender: str) -> dict:
    if sender not in sessions:
        sessions[sender] = _blank_session(sender)
    return sessions[sender]

def _blank_session(sender: str) -> dict:
    return {
        "sender":    sender,
        "state":     "IDLE",
        "product":   None,
        "quantity":  None,
        "placed_at": None,
        "delivery":  None,
    }

def reset_session(sender: str) -> None:
    sessions[sender] = _blank_session(sender)

# ---------------------------------------------------------------------------
# 4. HELPERS
# ---------------------------------------------------------------------------

def fill_placeholders(template: str, session: dict) -> str:
    return (
        template
        .replace("{product}",        session.get("product")   or "—")
        .replace("{quantity}",       session.get("quantity")  or "—")
        .replace("{placed_at}",      session.get("placed_at") or "—")
        .replace("{delivery}",       session.get("delivery")  or "—")
        .replace("{sender}",         session.get("sender")    or "—")
        .replace("{business_email}", BUSINESS_EMAIL)
    )


def find_state_by_keyword(text_lower: str):
    """
    Scan every state's keyword list.
    Returns the state name with the LONGEST matching keyword, or None.
    IDLE always has an empty keywords list so it is never returned here.
    """
    best_state, best_len = None, 0
    for state_name, state_def in STATES.items():
        for kw in state_def.get("keywords", []):
            if kw in text_lower and len(kw) > best_len:
                best_state, best_len = state_name, len(kw)
    return best_state


def scan_product_and_quantity(text: str) -> tuple:
    t    = text.lower()
    nums = list(re.finditer(r'\b(\d[\d,]*)\b', t))
    detected_product, product_pos = None, None
    for kw in sorted(PRODUCT_KEYWORDS.keys(), key=len, reverse=True):
        idx = t.find(kw)
        if idx != -1:
            detected_product, product_pos = PRODUCT_KEYWORDS[kw], idx
            break
    if not detected_product:
        return None, None
    qty = None
    if nums:
        closest = min(nums, key=lambda m: abs(m.start() - product_pos))
        qty = closest.group(1).replace(",", "")
    return detected_product, qty


def parse_delivery_date(text: str):
    today = datetime.now().date()
    t     = text.strip().lower()
    if t == "today":    return today.strftime("%A, %d %B %Y")
    if t == "tomorrow": return (today + timedelta(days=1)).strftime("%A, %d %B %Y")
    weekdays = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    for i, day in enumerate(weekdays):
        if f"next {day}" in t or t == day:
            ahead = (i - today.weekday() + 7) % 7 or 7
            return (today + timedelta(days=ahead)).strftime("%A, %d %B %Y")
    m = re.search(r'\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})\b', t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        try: return _date(y, mo, d).strftime("%A, %d %B %Y")
        except ValueError: pass
    months = {
        "jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,
        "apr":4,"april":4,"may":5,"jun":6,"june":6,"jul":7,"july":7,
        "aug":8,"august":8,"sep":9,"sept":9,"september":9,
        "oct":10,"october":10,"nov":11,"november":11,"dec":12,"december":12,
    }
    for pat, df in [
        (re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\s*(\d{4})?\b', t), True),
        (re.search(r'\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s*(\d{4})?\b', t), False),
    ]:
        if not pat: continue
        g = pat.groups()
        try:
            if df: d, ms, yr = int(g[0]), g[1], g[2]
            else:  ms, d, yr = g[0], int(g[1]), g[2]
            if ms not in months: continue
            mo = months[ms]
            y  = int(yr) if yr else (today.year if mo >= today.month else today.year + 1)
            return _date(y, mo, d).strftime("%A, %d %B %Y")
        except (ValueError, TypeError): continue
    return None


def build_product_info(product_name: str) -> str:
    p = PRODUCTS.get(product_name)
    if not p:
        return action_show_catalog({}, "", "")[0]
    return (
        f"{p['emoji']} *{product_name} -- Product Details*\n\n"
        f"📝 *About:* {p['description']}\n\n"
        f"📐 *Available Sizes:*\n   {p['sizes']}\n\n"
        f"✨ *Finish Options:*\n   {p['finish']}\n\n"
        f"🎯 *Best For:* {p['best_for']}\n\n"
        f"📦 *Minimum Order:* {p['min_qty']}\n\n"
        "─────────────────────\n"
        "Ready to order? Just say:\n"
        f"_'500 {product_name.lower()}'_ and we'll get started! 🚀"
    )

# ---------------------------------------------------------------------------
# 5. ACTION FUNCTIONS
# ---------------------------------------------------------------------------

def action_welcome(session: dict, msg_type: str, text: str):
    """Returns the welcome/greeting message. Handles hi, hello, hey, help, menu."""
    return fill_placeholders(STATES["WELCOME"]["message"], session), "IDLE"


def action_route_idle(session: dict, msg_type: str, text: str):
    """Free-form input handler — runs when no keyword matched."""
    t      = text.lower().strip()
    sender = session["sender"]

    # "info <product>" direct lookup
    if t.startswith("info "):
        query = t[5:].strip()
        for kw in sorted(PRODUCT_KEYWORDS.keys(), key=len, reverse=True):
            if kw in query:
                return build_product_info(PRODUCT_KEYWORDS[kw]), "IDLE"
        return STATES["FALLBACK"]["message"], "IDLE"

    # Product + quantity → start order chain
    product, quantity = scan_product_and_quantity(t)
    if product and quantity:
        session["product"]   = product
        session["quantity"]  = quantity
        session["placed_at"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
        logger.info(f"[ORDER] {sender} started -> {session}")
        return fill_placeholders(STATES["AWAITING_DATE"]["message"], session), "AWAITING_DATE"

    # Product mentioned with inquiry phrasing → info card
    if product:
        inquiry_kws = STATES["PRODUCT_INFO"].get("keywords", [])
        if any(kw in t for kw in inquiry_kws):
            return build_product_info(product), "IDLE"
        p = PRODUCTS.get(product, {})
        return (
            f"{p.get('emoji','🖨️')} *{product}* -- great choice!\n\n"
            "What would you like to do?\n\n"
            f"📋 Type *info {product.lower()}* -- sizes, finish & full details\n"
            f"📦 Tell us the quantity -- e.g. _'500 {product.lower()}'_"
        ), "IDLE"

    return STATES["FALLBACK"]["message"], "IDLE"


def action_start_order(session: dict, msg_type: str, text: str):
    return fill_placeholders(STATES["AWAITING_PRODUCT"]["message"], session), "AWAITING_PRODUCT"


def action_detect_product_and_quantity(session: dict, msg_type: str, text: str):
    if msg_type != "text":
        return "Please *type* the product and quantity.\n_Example: 500 visiting cards_", "AWAITING_PRODUCT"
    product, quantity = scan_product_and_quantity(text.lower())
    if not product:
        return (
            "🤔 I couldn't identify a product.\n\n"
            "Please mention a product and quantity:\n"
            "_'500 visiting cards'_ or _'200 flyers'_\n\n"
            "Type *Catalog* to see all products."
        ), "AWAITING_PRODUCT"
    session["product"]   = product
    session["quantity"]  = quantity or "As requested"
    session["placed_at"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
    logger.info(f"[ORDER] {session['sender']} product set -> {session}")
    return fill_placeholders(STATES["AWAITING_DATE"]["message"], session), "AWAITING_DATE"


def action_parse_delivery_date(session: dict, msg_type: str, text: str):
    if msg_type != "text":
        return (
            f"📅 Please *type your preferred delivery date.*\n"
            f"   _Example: 10th June, 15/06/2025, next Monday_\n\n"
            f"🎨 And email your design to *{BUSINESS_EMAIL}*"
        ), "AWAITING_DATE"
    parsed = parse_delivery_date(text)
    if not parsed:
        return (
            "🤔 I didn't quite catch that date. Please try:\n\n"
            "• _10th June_\n• _15/06/2025_\n• _June 15_\n• _Next Monday_"
        ), "AWAITING_DATE"
    session["delivery"] = parsed
    logger.info(f"[ORDER] {session['sender']} date set -> {session}")
    reply = fill_placeholders(STATES["CONFIRMED"]["message"], session)
    reset_session(session["sender"])
    return reply, "IDLE"


def action_finalize_order(session: dict, msg_type: str, text: str):
    reset_session(session["sender"])
    return "", "IDLE"


WEEKDAY_HOURS = "10:00 AM – 8:00 PM"
SUNDAY_HOURS  = "10:00 AM – 6:00 PM"

def action_show_hours(session: dict, msg_type: str, text: str):
    today_name   = datetime.now().strftime("%A")
    t            = text.lower()
    sunday_kws   = [
        "sunday", "holiday", "holidays", "public holiday", "national holiday",
        "open on sunday", "open sunday", "working on sunday",
        "open on holiday", "open on holidays", "are you open on sunday",
        "do you work on sunday", "open during holiday", "available on sunday",
    ]
    asked_sunday = any(kw in t for kw in sunday_kws)

    if asked_sunday:
        return (
            "🟢 *Yes! Citizen Print is open on Sundays.*\n\n"
            f"🕒 *Sunday Hours:*  {SUNDAY_HOURS}\n"
            f"🕒 *Mon – Sat:*     {WEEKDAY_HOURS}\n\n"
            "📌 *Note:* We are closed only on *national public holidays*.\n"
            "   Orders placed on holidays are processed the next working day.\n\n"
            "📦 Type *Order* to place an order\n"
            "📋 Type *Catalog* to see our products"
        ), "IDLE"
    elif today_name == "Sunday":
        return (
            f"🟢 *Today is Sunday — we're open!*\n\n"
            f"🕒 *Today's Hours:* {SUNDAY_HOURS}\n"
            f"🕒 *Mon – Sat:*     {WEEKDAY_HOURS}\n\n"
            "📦 Type *Order* to place an order\n"
            "📋 Type *Catalog* to see our products"
        ), "IDLE"
    else:
        return (
            f"🟢 *Citizen Print — Today is {today_name}*\n\n"
            f"🕒 *Today's Hours:* {WEEKDAY_HOURS}\n"
            f"🕒 *Sunday:*        {SUNDAY_HOURS}\n\n"
            "📦 Type *Order* to place an order\n"
            "📋 Type *Catalog* to see our products"
        ), "IDLE"


def action_show_catalog(session: dict, msg_type: str, text: str):
    lines = "\n".join(
        f"  {p['emoji']} *{name}* -- {p['description']}"
        for name, p in PRODUCTS.items()
    )
    return (
        "📋 *Citizen Print -- What We Offer*\n\n"
        "We provide printing for:\n\n"
        f"{lines}\n\n"
        "💬 Type a product name for full details.\n"
        "   _Example: 'Tell me about banners'_\n\n"
        "📦 Ready to order? Just say:\n"
        "   _'500 visiting cards'_ or _'200 flyers'_"
    ), "IDLE"


def action_show_product_info(session: dict, msg_type: str, text: str):
    t = text.lower()
    for kw in sorted(PRODUCT_KEYWORDS.keys(), key=len, reverse=True):
        if kw in t:
            return build_product_info(PRODUCT_KEYWORDS[kw]), "IDLE"
    return action_show_catalog(session, msg_type, text)

# ---------------------------------------------------------------------------
# 6. ACTION MAP
# ---------------------------------------------------------------------------
ACTION_MAP: dict = {
    "welcome":                     action_welcome,
    "route_idle":                  action_route_idle,
    "start_order":                 action_start_order,
    "detect_product_and_quantity": action_detect_product_and_quantity,
    "parse_delivery_date":         action_parse_delivery_date,
    "finalize_order":              action_finalize_order,
    "show_hours":                  action_show_hours,
    "show_catalog":                action_show_catalog,
    "show_product_info":           action_show_product_info,
}

# ---------------------------------------------------------------------------
# 7. ROUTER
# ---------------------------------------------------------------------------

def route_message(sender: str, msg_type: str, msg: dict) -> str:
    session    = get_session(sender)
    state_name = session["state"]
    text       = msg.get("text", {}).get("body", "").strip() if msg_type == "text" else ""
    text_lower = text.lower()

    logger.info(f"[ROUTER] {sender} | state={state_name} | input='{text or msg_type}'")

    matched = find_state_by_keyword(text_lower)
    is_esc  = matched in ESCAPE_STATES if matched else False

    # ── Mid-flow: waiting for product or date ─────────────────────────────
    if state_name in MID_FLOW_STATES and not is_esc:
        fn = ACTION_MAP.get(STATES[state_name].get("action"))
        if fn:
            reply, next_state = fn(session, msg_type, text)
        else:
            reply      = fill_placeholders(STATES[state_name]["message"], session)
            next_state = STATES[state_name]["next_state"]

    # ── Keyword matched ───────────────────────────────────────────────────
    elif matched:
        if is_esc and state_name in MID_FLOW_STATES:
            reset_session(sender)
            session = get_session(sender)
            logger.info(f"[ESCAPE] {sender} left {state_name} via '{matched}'")

        fn = ACTION_MAP.get(STATES[matched].get("action"))
        if fn:
            reply, next_state = fn(session, msg_type, text)
        else:
            reply      = fill_placeholders(STATES[matched]["message"], session)
            next_state = STATES[matched]["next_state"]

    # ── No keyword matched — free-form input ──────────────────────────────
    else:
        reply, next_state = action_route_idle(session, msg_type, text)

    # ── Persist next_state ────────────────────────────────────────────────
    live = get_session(sender)
    if next_state in STATES:
        live["state"] = next_state

    if not reply:
        reply = fill_placeholders(STATES["WELCOME"]["message"], live)

    logger.info(f"[ROUTER] {sender} -> {next_state}")
    return reply

# ---------------------------------------------------------------------------
# 8. INFRASTRUCTURE
# ---------------------------------------------------------------------------

async def send_whatsapp_message(recipient_id: str, text: str) -> None:
    url     = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to":   recipient_id,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            logger.error(f"[SEND] Failed for {recipient_id}: {r.text}")


@app.post("/webhook")
async def handle(request: Request):
    data = await request.json()
    try:
        value = data["entry"][0]["changes"][0]["value"]
        if "messages" in value:
            msg      = value["messages"][0]
            sender   = msg["from"]
            msg_type = msg.get("type")
            try:
                reply = route_message(sender, msg_type, msg)
            except Exception as e:
                logger.exception(f"[ERROR] route_message crashed for {sender}: {e}")
                reply = (
                    "⚠️ Something went wrong on our end.\n"
                    "Please try again or type *Hi* to restart."
                )
            await send_whatsapp_message(sender, reply)
    except Exception as e:
        logger.exception(f"[ERROR] Webhook handler: {e}")
    return {"status": "success"}


@app.get("/webhook")
async def verify(request: Request):
    if request.query_params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(request.query_params.get("hub.challenge"))
    return "Failed"
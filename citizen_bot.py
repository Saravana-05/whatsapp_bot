import httpx
import json
import re
import sqlite3
import logging
from datetime import datetime, timedelta, date as _date
from pathlib import Path
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app    = FastAPI()

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------
ACCESS_TOKEN    = "EAAVYo9qkDuQBRfDv7YXE5mlURaxmm0wZBaJZAiE8YIYxHZBoDR6kXqBpAlmGqDl3pC348WQnP95M8CsXZCuPWZCm1DIj6nmmZCYQ3Sy2uNtKsHgXC8c8RstqYv2WIrsFRhffDQ06ZAydM9cLaBQoXUHnmMrTp2cD8uLcCM2tnMyZCZBHe27duRvuaGRCXp1mmXaryZByZAb7GUnWypeEsDoCSFFl2lsMs27DM7uY7d6z1gH9FlLboWHMZCeBfX74TDVTdgnmaWEDszlgpm9y1qRMLgCvgZCZAT"
PHONE_NUMBER_ID = "1003362262871598"
VERIFY_TOKEN    = "my_cafe_bot"
BUSINESS_EMAIL  = "designs@citizenprint.com"

# ---------------------------------------------------------------------------
# 2. DATABASE  — SQLite, same folder as this file
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).parent / "citizenprint.db"

def get_db() -> sqlite3.Connection:
    """Open a DB connection with row_factory so rows behave like dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def db_fetch_all_products() -> list[sqlite3.Row]:
    """Return all active products ordered by name."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM products WHERE active = 1 ORDER BY name"
        ).fetchall()


def db_fetch_product(name: str) -> sqlite3.Row | None:
    """Return a single product by exact name, or None."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM products WHERE active = 1 AND LOWER(name) = LOWER(?)",
            (name,)
        ).fetchone()


def db_get_product_keywords() -> dict:
    """
    Build the product_keywords mapping live from the DB.
    Falls back to flow.json product_keywords if DB is unavailable.
    Both singular and plural forms are added automatically.
    """
    try:
        rows = db_fetch_all_products()
        kw_map = {}
        for row in rows:
            name  = row["name"]
            lower = name.lower()
            kw_map[lower]           = name        # "visiting cards"
            kw_map[lower.rstrip("s")] = name      # "visiting card"
        return kw_map
    except Exception as e:
        logger.warning(f"[DB] product keyword fallback to flow.json: {e}")
        return FLOW.get("product_keywords", {})

# ---------------------------------------------------------------------------
# 3. LOAD flow.json
# ---------------------------------------------------------------------------
FLOW_PATH = Path(__file__).parent / "flow.json"

def load_flow() -> dict:
    with open(FLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

FLOW   = load_flow()
STATES = FLOW["states"]

# Product keywords: loaded from DB at startup (refreshed on each call if needed)
PRODUCT_KEYWORDS: dict = {}

def refresh_product_keywords():
    """Reload product keywords from DB into the global map."""
    global PRODUCT_KEYWORDS
    PRODUCT_KEYWORDS = db_get_product_keywords()
    # Also honour any extra mappings in flow.json
    PRODUCT_KEYWORDS.update(FLOW.get("product_keywords", {})) 

refresh_product_keywords()

# States that interrupt mid-flow conversation
ESCAPE_STATES   = {"WELCOME", "CATALOG", "HOURS", "SUNDAY_HOLIDAY", "ORDER", "PRODUCT_INFO"}
# States waiting for a specific customer reply
MID_FLOW_STATES = {"AWAITING_PRODUCT", "AWAITING_DATE"}

# ---------------------------------------------------------------------------
# 4. SESSION STORE
# ---------------------------------------------------------------------------
sessions: dict = {}

def get_session(sender: str) -> dict:
    if sender not in sessions:
        sessions[sender] = _blank_session(sender)
    return sessions[sender]

def _blank_session(sender: str) -> dict:
    return {
        "sender":    sender,
        "state":     "WELCOME",   # default state — no IDLE
        "product":   None,
        "quantity":  None,
        "placed_at": None,
        "delivery":  None,
    }

def reset_session(sender: str) -> None:
    sessions[sender] = _blank_session(sender)

# ---------------------------------------------------------------------------
# 5. HELPERS
# ---------------------------------------------------------------------------

def fill(template: str, session: dict) -> str:
    """Replace {placeholders} with live session values."""
    return (
        template
        .replace("{product}",        session.get("product")   or "—")
        .replace("{quantity}",       session.get("quantity")  or "—")
        .replace("{placed_at}",      session.get("placed_at") or "—")
        .replace("{delivery}",       session.get("delivery")  or "—")
        .replace("{sender}",         session.get("sender")    or "—")
        .replace("{business_email}", BUSINESS_EMAIL)
    )


def find_state_by_keyword(text_lower: str) -> str | None:
    """
    Scan every state's keyword list in flow.json.
    Return the state with the longest matching keyword (longest-wins).
    WELCOME has keywords; no state called IDLE exists any more.
    """
    best_state, best_len = None, 0
    for state_name, state_def in STATES.items():
        for kw in state_def.get("keywords", []):
            if kw in text_lower and len(kw) > best_len:
                best_state, best_len = state_name, len(kw)
    return best_state


def scan_product_and_quantity(text: str) -> tuple:
    """Detect a product name and the closest number in free text."""
    t    = text.lower()
    nums = list(re.finditer(r'\b(\d[\d,]*)\b', t))
    product, pos = None, None
    for kw in sorted(PRODUCT_KEYWORDS.keys(), key=len, reverse=True):
        idx = t.find(kw)
        if idx != -1:
            product, pos = PRODUCT_KEYWORDS[kw], idx
            break
    if not product:
        return None, None
    qty = None
    if nums:
        closest = min(nums, key=lambda m: abs(m.start() - pos))
        qty = closest.group(1).replace(",", "")
    return product, qty


def parse_delivery_date(text: str) -> str | None:
    """Parse a customer-typed date into 'Monday, 16 June 2026' or None."""
    today = datetime.now().date()
    t     = text.strip().lower()
    if t == "today":    return today.strftime("%A, %d %B %Y")
    if t == "tomorrow": return (today + timedelta(1)).strftime("%A, %d %B %Y")
    days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    for i, d in enumerate(days):
        if f"next {d}" in t or t == d:
            ahead = (i - today.weekday() + 7) % 7 or 7
            return (today + timedelta(ahead)).strftime("%A, %d %B %Y")
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


def build_product_card(row) -> str:
    """
    Build a formatted product detail card from a DB row (sqlite3.Row).
    row fields: name, emoji, description, sizes, finish, best_for, min_qty
    """
    name = row["name"]
    return (
        f"{row['emoji']} *{name} — Product Details*\n\n"
        f"📝 *About:* {row['description']}\n\n"
        f"📐 *Available Sizes:*\n   {row['sizes']}\n\n"
        f"✨ *Finish Options:*\n   {row['finish']}\n\n"
        f"🎯 *Best For:* {row['best_for']}\n\n"
        f"📦 *Minimum Order:* {row['min_qty']}\n\n"
        "─────────────────────\n"
        "Ready to order? Just say:\n"
        f"_'500 {name.lower()}'_ and we'll get started! 🚀"
    )

# ---------------------------------------------------------------------------
# 6. ACTION FUNCTIONS
#    Each receives (session, msg_type, text) and returns (reply, next_state).
#    ACTION_MAP below maps the flow.json "action" string to these functions.
# ---------------------------------------------------------------------------

def action_welcome(session: dict, msg_type: str, text: str):
    """hi / hello / hey — return the welcome greeting."""
    return fill(STATES["WELCOME"]["message"], session), "WELCOME"


def action_free_text(session: dict, msg_type: str, text: str):
    """
    Handles any message that matched no keyword in flow.json.
    Priority:
      1. "info <product>"  → product detail card from DB
      2. product + qty     → start order chain
      3. product only      → ask intent (info or order?)
      4. fallback          → FALLBACK message
    """
    t      = text.lower().strip()
    sender = session["sender"]

    # 1. "info <product>"
    if t.startswith("info "):
        query = t[5:].strip()
        for kw in sorted(PRODUCT_KEYWORDS.keys(), key=len, reverse=True):
            if kw in query:
                row = db_fetch_product(PRODUCT_KEYWORDS[kw])
                if row:
                    return build_product_card(row), "WELCOME"
        return STATES["FALLBACK"]["message"], "WELCOME"

    # 2. Product + quantity → begin order
    product, qty = scan_product_and_quantity(t)
    if product and qty:
        session["product"]   = product
        session["quantity"]  = qty
        session["placed_at"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
        logger.info(f"[ORDER] {sender} started -> {session}")
        return fill(STATES["AWAITING_DATE"]["message"], session), "AWAITING_DATE"

    # 3. Product name only
    if product:
        inquiry_kws = STATES["PRODUCT_INFO"].get("keywords", [])
        if any(kw in t for kw in inquiry_kws):
            row = db_fetch_product(product)
            return (build_product_card(row) if row else STATES["FALLBACK"]["message"]), "WELCOME"
        row   = db_fetch_product(product)
        emoji = row["emoji"] if row else "🖨️"
        return (
            f"{emoji} *{product}* — great choice!\n\n"
            "What would you like to do?\n\n"
            f"📋 Type *info {product.lower()}* — sizes, finish & details\n"
            f"📦 Tell us the quantity — e.g. _'500 {product.lower()}'_"
        ), "WELCOME"

    # 4. Fallback
    return STATES["FALLBACK"]["message"], "WELCOME"


def action_start_order(session: dict, msg_type: str, text: str):
    """Customer typed 'order' — prompt for product and quantity."""
    return fill(STATES["AWAITING_PRODUCT"]["message"], session), "AWAITING_PRODUCT"


def action_detect_product_and_quantity(session: dict, msg_type: str, text: str):
    """
    AWAITING_PRODUCT state.
    Expects a product name + quantity from the customer.
    On success: writes product, quantity, placed_at into session → AWAITING_DATE.
    On failure: stays in AWAITING_PRODUCT.
    """
    if msg_type != "text":
        return "Please *type* the product and quantity.\n_Example: 500 visiting cards_", "AWAITING_PRODUCT"

    product, qty = scan_product_and_quantity(text.lower())
    if not product:
        return (
            "🤔 I couldn't identify a product.\n\n"
            "Please mention a product and quantity:\n"
            "_'500 visiting cards'_ or _'200 flyers'_\n\n"
            "Type *Catalog* to see all products."
        ), "AWAITING_PRODUCT"

    session["product"]   = product
    session["quantity"]  = qty or "As requested"
    session["placed_at"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
    logger.info(f"[ORDER] {session['sender']} product set -> {session}")
    return fill(STATES["AWAITING_DATE"]["message"], session), "AWAITING_DATE"


def action_parse_delivery_date(session: dict, msg_type: str, text: str):
    """
    AWAITING_DATE state.
    Expects a delivery date from the customer.
    On success: writes delivery into session, sends CONFIRMED message, resets session.
    On failure: stays in AWAITING_DATE.
    """
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
    reply = fill(STATES["CONFIRMED"]["message"], session)
    reset_session(session["sender"])
    return reply, "WELCOME"


def action_finalize_order(session: dict, msg_type: str, text: str):
    """Safety reset for CONFIRMED state — reply already sent above."""
    reset_session(session["sender"])
    return "", "WELCOME"


WEEKDAY_HOURS = "10:00 AM – 8:00 PM"
SUNDAY_HOURS  = "10:00 AM – 6:00 PM"

def action_show_hours(session: dict, msg_type: str, text: str):
    """Return correct hours message based on day / Sunday inquiry."""
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
            "📌 Closed only on *national public holidays*.\n"
            "   Orders placed on holidays are processed the next working day.\n\n"
            "📦 Type *Order* to place an order\n"
            "📋 Type *Catalog* to see our products"
        ), "WELCOME"
    elif today_name == "Sunday":
        return (
            f"🟢 *Today is Sunday — we're open!*\n\n"
            f"🕒 *Today's Hours:* {SUNDAY_HOURS}\n"
            f"🕒 *Mon – Sat:*     {WEEKDAY_HOURS}\n\n"
            "📦 Type *Order* to place an order\n"
            "📋 Type *Catalog* to see our products"
        ), "WELCOME"
    else:
        return (
            f"🟢 *Citizen Print — Today is {today_name}*\n\n"
            f"🕒 *Today's Hours:* {WEEKDAY_HOURS}\n"
            f"🕒 *Sunday:*        {SUNDAY_HOURS}\n\n"
            "📦 Type *Order* to place an order\n"
            "📋 Type *Catalog* to see our products"
        ), "WELCOME"


def action_show_catalog(session: dict, msg_type: str, text: str):
    """
    ACTION KEY: "show_catalog"
    Fetches all active products from the database and builds
    the catalog list to send back to the customer on WhatsApp.
    """
    rows = db_fetch_all_products()

    if not rows:
        return (
            "📋 *Citizen Print — Product Catalog*\n\n"
            "Our catalog is being updated. Please check back shortly!\n\n"
            "📦 Type *Order* to place an order\n"
            "🕒 Type *Hours* for our timings"
        ), "WELCOME"

    lines = "\n".join(
        f"  {row['emoji']} *{row['name']}* — {row['description']}"
        for row in rows
    )
    return (
        "📋 *Citizen Print — What We Offer*\n\n"
        "We provide printing for:\n\n"
        f"{lines}\n\n"
        "💬 Type a product name for full details.\n"
        "   _Example: 'Tell me about banners'_\n\n"
        "📦 Ready to order? Just say:\n"
        "   _'500 visiting cards'_ or _'200 flyers'_"
    ), "WELCOME"


def action_show_product_info(session: dict, msg_type: str, text: str):
    """
    ACTION KEY: "show_product_info"
    Detects which product the customer asked about,
    fetches its details from the database, and returns a formatted card.
    Falls back to the full catalog if no product is identified.
    """
    t = text.lower()
    for kw in sorted(PRODUCT_KEYWORDS.keys(), key=len, reverse=True):
        if kw in t:
            row = db_fetch_product(PRODUCT_KEYWORDS[kw])
            if row:
                return build_product_card(row), "WELCOME"
    # No product matched → show full catalog from DB
    return action_show_catalog(session, msg_type, text)

# ---------------------------------------------------------------------------
# 7. ACTION MAP
#    flow.json "action" string  →  Python function above
#
#    To add a new action:
#      1. Write the function above
#      2. Add an entry here
#      3. Set "action": "<key>" in the relevant flow.json state
# ---------------------------------------------------------------------------
ACTION_MAP: dict = {
    "welcome":                     action_welcome,
    "free_text":                   action_free_text,
    "start_order":                 action_start_order,
    "detect_product_and_quantity": action_detect_product_and_quantity,
    "parse_delivery_date":         action_parse_delivery_date,
    "finalize_order":              action_finalize_order,
    "show_hours":                  action_show_hours,
    "show_catalog":                action_show_catalog,      # ← fetches from DB
    "show_product_info":           action_show_product_info, # ← fetches from DB
}

# ---------------------------------------------------------------------------
# 8. ROUTER  — zero business logic lives here
# ---------------------------------------------------------------------------

def route_message(sender: str, msg_type: str, msg: dict) -> str:
    session    = get_session(sender)
    state_name = session["state"]
    text       = msg.get("text", {}).get("body", "").strip() if msg_type == "text" else ""
    text_lower = text.lower()

    logger.info(f"[ROUTER] {sender} | state={state_name} | input='{text or msg_type}'")

    matched = find_state_by_keyword(text_lower)
    is_esc  = matched in ESCAPE_STATES if matched else False

    # ── Mid-flow: waiting for product or date ──────────────────────────────
    if state_name in MID_FLOW_STATES and not is_esc:
        fn = ACTION_MAP.get(STATES[state_name].get("action"))
        if fn:
            reply, next_state = fn(session, msg_type, text)
        else:
            reply      = fill(STATES[state_name]["message"], session)
            next_state = STATES[state_name]["next_state"]

    # ── Keyword matched ────────────────────────────────────────────────────
    elif matched:
        if is_esc and state_name in MID_FLOW_STATES:
            reset_session(sender)
            session = get_session(sender)
            logger.info(f"[ESCAPE] {sender} left {state_name} via '{matched}'")

        fn = ACTION_MAP.get(STATES[matched].get("action"))
        if fn:
            reply, next_state = fn(session, msg_type, text)
        else:
            reply      = fill(STATES[matched]["message"], session)
            next_state = STATES[matched]["next_state"]

    # ── No keyword matched — free-form input ──────────────────────────────
    else:
        reply, next_state = action_free_text(session, msg_type, text)

    # ── Persist next_state ─────────────────────────────────────────────────
    live = get_session(sender)
    if next_state in STATES:
        live["state"] = next_state

    if not reply:
        reply = fill(STATES["WELCOME"]["message"], live)

    logger.info(f"[ROUTER] {sender} -> {next_state}")
    return reply

# ---------------------------------------------------------------------------
# 9. INFRASTRUCTURE
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
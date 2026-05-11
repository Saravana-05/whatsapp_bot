import httpx
import re
import logging
from datetime import datetime, timedelta
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# --- 1. CONFIGURATION ---
ACCESS_TOKEN      = "EAAVYo9qkDuQBReDDTzK1HQJkgjQ31NzRB49PZC1G9Ob7QmqvhVd396qfrRr5iLGdiJespRdJ9MLuLrsTgZA8EyIsDPilOxekNNcGmKkKN8rR98WpUXZAQGyoiDmZATHLDGvRBiSge2AXgcpOCz7JZCQKhPXpKtkwFyZBQLz3ByW5whAXcIVAUZBAF0UTyukcwAJKOHpXoG4rGWrIZAHGubAFkVGtSefjiI99zV3wO4vFK2IxARgfIFTMfOA4O2oj8q0G5wpCyloZA11Is6A9jX6V50TAW"
PHONE_NUMBER_ID   = "1003362262871598"
VERIFY_TOKEN      = "my_cafe_bot"
BUSINESS_EMAIL    = "designs@citizenprint.com"  

# --- 2. STATE STORAGE ---
user_states = {}   
user_orders = {}   

# --- 3. PRODUCT CATALOG ---
# PRODUCT_DETAILS: Full description for each product.
# Format per product:
#   "display_name"  : shown in order confirmations
#   "emoji"         : used in messages
#   "description"   : what the product is
#   "sizes"         : available sizes / formats
#   "finish"        : finishing options
#   "best_for"      : ideal use cases
#   "min_qty"       : minimum order quantity
PRODUCT_DETAILS = {
    "Visiting Cards": {
        "display_name": "Visiting Cards",
        "emoji": "💼",
        "description": "Professional visiting cards to make a lasting first impression.",
        "sizes": "Standard (3.5\" × 2\") | Square (2.5\" × 2.5\") | Slim (3.5\" × 1.5\")",
        "finish": "Matte | Glossy | Soft Touch | UV Spot | Foil",
        "best_for": "Professionals, freelancers, business networking",
        "min_qty": "100 cards",
    },
    "Business Cards": {
        "display_name": "Business Cards",
        "emoji": "🏢",
        "description": "Premium business cards with corporate-grade print quality.",
        "sizes": "Standard (3.5\" × 2\") | Premium (3.5\" × 2.5\")",
        "finish": "Matte | Glossy | Embossed | Foil | Velvet Lamination",
        "best_for": "Corporate professionals, companies, startups",
        "min_qty": "100 cards",
    },
    "Flyers": {
        "display_name": "Flyers",
        "emoji": "📄",
        "description": "Eye-catching single-sheet flyers for promotions and announcements.",
        "sizes": "A4 | A5 | A6 | DL (⅓ A4)",
        "finish": "Matte | Glossy | Uncoated",
        "best_for": "Events, sales promotions, product launches, offers",
        "min_qty": "100 flyers",
    },
    "Pamphlets": {
        "display_name": "Pamphlets",
        "emoji": "📰",
        "description": "Folded pamphlets ideal for detailed product or service information.",
        "sizes": "A4 Bi-fold | A4 Tri-fold | A5 Bi-fold",
        "finish": "Matte | Glossy",
        "best_for": "Product info, service guides, educational material",
        "min_qty": "100 pamphlets",
    },
    "Brochures": {
        "display_name": "Brochures",
        "emoji": "📑",
        "description": "Multi-panel brochures for detailed brand storytelling.",
        "sizes": "A4 Tri-fold | A4 Z-fold | A4 Bi-fold | A5 Bi-fold",
        "finish": "Matte | Glossy | Soft Touch Lamination",
        "best_for": "Company profiles, product catalogs, tourism, real estate",
        "min_qty": "50 brochures",
    },
    "Banners": {
        "display_name": "Banners",
        "emoji": "🎌",
        "description": "Large-format banners for high-visibility indoor and outdoor use.",
        "sizes": "2×4 ft | 3×6 ft | 4×8 ft | Custom sizes available",
        "finish": "Vinyl (Outdoor) | Fabric (Indoor) | Mesh (Windy areas)",
        "best_for": "Events, shop fronts, trade shows, outdoor advertising",
        "min_qty": "1 banner",
    },
    "Posters": {
        "display_name": "Posters",
        "emoji": "🖼️",
        "description": "Vibrant full-colour posters to display your message boldly.",
        "sizes": "A3 | A2 | A1 | A0 | Custom",
        "finish": "Matte | Glossy | Satin",
        "best_for": "Events, advertising, décor, announcements",
        "min_qty": "10 posters",
    },
    "Stickers": {
        "display_name": "Stickers",
        "emoji": "🏷️",
        "description": "Custom-cut stickers in any shape for branding and packaging.",
        "sizes": "Circle | Square | Rectangle | Custom die-cut shapes",
        "finish": "Matte | Glossy | Transparent | Waterproof",
        "best_for": "Product labels, packaging, branding, giveaways",
        "min_qty": "100 stickers",
    },
    "Letterheads": {
        "display_name": "Letterheads",
        "emoji": "📋",
        "description": "Branded letterheads to give your official correspondence a professional look.",
        "sizes": "A4 (standard)",
        "finish": "Matte | Glossy | Uncoated Bond Paper",
        "best_for": "Business letters, quotes, invoices, official documents",
        "min_qty": "100 sheets",
    },
    "Envelopes": {
        "display_name": "Envelopes",
        "emoji": "✉️",
        "description": "Custom-printed envelopes with your logo and return address.",
        "sizes": "DL | C5 | C4 | A4 Pocket",
        "finish": "White | Brown Kraft | Custom colour",
        "best_for": "Corporate mailers, invitations, official correspondence",
        "min_qty": "100 envelopes",
    },
    "ID Cards": {
        "display_name": "ID Cards",
        "emoji": "🪪",
        "description": "Durable PVC ID cards for staff, students, and membership use.",
        "sizes": "CR80 Standard (3.375\" × 2.125\") — wallet size",
        "finish": "Glossy PVC | Frosted | with or without lamination pouch",
        "best_for": "Employee IDs, student cards, membership cards, access cards",
        "min_qty": "25 cards",
    },
    "Calendars": {
        "display_name": "Calendars",
        "emoji": "📅",
        "description": "Customised wall and desk calendars branded with your logo.",
        "sizes": "Wall Calendar (A3/A4) | Desk Calendar (A5) | Pocket Calendar",
        "finish": "Matte | Glossy | Spiral-bound | Staple-bound",
        "best_for": "Corporate gifting, brand promotion, offices, year-end gifts",
        "min_qty": "25 calendars",
    },
}

# PRODUCT_CATALOG: Keyword → display name mapping (used for detection)
# Add synonyms here; the display name must match a key in PRODUCT_DETAILS above.
PRODUCT_CATALOG = {
    "visiting card":    "Visiting Cards",
    "visiting cards":   "Visiting Cards",
    "business card":    "Business Cards",
    "business cards":   "Business Cards",
    "flyer":            "Flyers",
    "flyers":           "Flyers",
    "pamphlet":         "Pamphlets",
    "pamphlets":        "Pamphlets",
    "brochure":         "Brochures",
    "brochures":        "Brochures",
    "banner":           "Banners",
    "banners":          "Banners",
    "poster":           "Posters",
    "posters":          "Posters",
    "sticker":          "Stickers",
    "stickers":         "Stickers",
    "letterhead":       "Letterheads",
    "letterheads":      "Letterheads",
    "envelope":         "Envelopes",
    "envelopes":        "Envelopes",
    "id card":          "ID Cards",
    "id cards":         "ID Cards",
    "calendar":         "Calendars",
    "calendars":        "Calendars",
}

# Keywords that indicate the customer is ASKING ABOUT a product (not ordering).
# IMPORTANT: only use multi-word or unambiguous phrases here.
# Single common words like "available", "options", "about" were removed
# because they appear in normal order sentences and cause false matches.
INQUIRY_KEYWORDS = [
    "what is", "what are", "tell me about", "more info", "information",
    "describe", "description", "explain",
    "do you have", "do you sell", "do you provide", "do you offer",
    "what do you offer", "what do you provide", "what do you sell",
    "what products", "what services", "your products", "your services",
    "how much", "what is the price", "what are the rates",
    "specification", "what sizes", "what finish",
]

# --- 4. FUNCTION BLOCKS ---

def get_welcome():
    return (
        "🖨️ *Welcome to Citizen Print!*\n\n"
        "How can I help you today?\n\n"
        "📦 Type *Order* to browse our catalog\n"
        "🛍️ Or just tell me what you need!\n"
        "   _Example: 'I need 500 visiting cards'_\n"
        "🕒 Type *Hours* to know our timings\n"
        "📋 Type *Catalog* to see all products"
    )


def get_catalog():
    """Short product list — shown when customer types 'catalog' or 'products'."""
    lines = "\n".join(
        f"  {p['emoji']} *{p['display_name']}* — {p['description']}"
        for p in PRODUCT_DETAILS.values()
    )
    return (
        "📋 *Citizen Print — What We Offer*\n\n"
        "We provide printing assistance for the following products:\n\n"
        f"{lines}\n\n"
        "💬 Type the product name to get full details.\n"
        "   _Example: 'Tell me about banners' or 'visiting card info'_\n\n"
        "📦 Ready to order? Just say:\n"
        "   _'500 visiting cards'_ or _'Order 200 flyers'_"
    )


def get_product_description(product_name):
    """
    Returns a detailed description card for a specific product.
    Called when customer asks about a product without placing an order.
    """
    p = PRODUCT_DETAILS.get(product_name)
    if not p:
        return None
    return (
        f"{p['emoji']} *{p['display_name']} — Product Details*\n\n"
        f"📝 *About:* {p['description']}\n\n"
        f"📐 *Available Sizes:*\n   {p['sizes']}\n\n"
        f"✨ *Finish Options:*\n   {p['finish']}\n\n"
        f"🎯 *Best For:* {p['best_for']}\n\n"
        f"📦 *Minimum Order:* {p['min_qty']}\n\n"
        "─────────────────────\n"
        "Ready to order? Just say:\n"
        f"_'500 {p['display_name'].lower()}'_ and we'll get started! 🚀"
    )


def is_product_inquiry(text_lower):
    """
    Returns True if the message looks like a question or inquiry
    about products rather than an order.
    e.g. 'what products do you have', 'tell me about banners', 'do you sell stickers'
    """
    return any(kw in text_lower for kw in INQUIRY_KEYWORDS)


def start_order_flow(sender):
    """Called when customer types 'order' without specifying a product."""
    user_states[sender] = "AWAITING_PRODUCT"
    return (
        "📦 *Let's start your order!*\n\n"
        "Please tell me *what product* you need and *how many*.\n\n"
        "_Example: 500 visiting cards, 200 flyers, 1000 stickers_"
    )


def detect_product_and_quantity(text):
    """
    Scans a free-text message for a known product and an optional quantity.
    Finds the number that appears CLOSEST to the product keyword,
    so '500 banners' and 'banners 500' both work correctly.
    Returns (product_display_name, quantity_str) or (None, None).
    """
    text_lower = text.lower()

    # Find all numbers and their positions in the text
    number_matches = list(re.finditer(r'\b(\d[\d,]*)\b', text_lower))

    # Match the longest product keyword first (so "visiting cards" beats "cards")
    detected_product = None
    product_pos = None
    for keyword in sorted(PRODUCT_CATALOG.keys(), key=len, reverse=True):
        idx = text_lower.find(keyword)
        if idx != -1:
            detected_product = PRODUCT_CATALOG[keyword]
            product_pos = idx
            break

    if not detected_product:
        return None, None

    # Pick the number closest to the product keyword position
    quantity = None
    if number_matches:
        closest = min(number_matches, key=lambda m: abs(m.start() - product_pos))
        quantity = closest.group(1).replace(',', '')

    return detected_product, quantity


def confirm_catalog_order(sender, product, quantity):
    """
    Called when product + quantity is detected.
    Immediately confirms the order, asks ONLY for delivery date,
    and instructs customer to email the design.
    """
    # Stamp the order-placed time in IST
    now = datetime.now()
    order_time = now.strftime("%d %b %Y, %I:%M %p")

    user_orders[sender] = {
        "product":        product,
        "quantity":       quantity or "As requested",
        "order_placed_at": order_time,
        "delivery_date":  None,
    }
    user_states[sender] = "AWAITING_DATE"

    qty_display = f"{quantity} " if quantity else ""
    return (
        f"✅ *Your Order is Placed!*\n\n"
        f"🛍️ *Product:*  {product}\n"
        f"🔢 *Quantity:* {qty_display}{product.lower()}\n"
        f"🕒 *Order Placed:* {order_time}\n\n"
        "To complete your order, we need one more thing:\n\n"
        "📅 *Please tell us your preferred delivery date.*\n"
        "   _Example: 10th June, 15/06/2025, next Monday_\n\n"
        "🎨 *Please share your design file to our email:*\n"
        f"   📧 *{BUSINESS_EMAIL}*\n"
        "   _Mention your WhatsApp number in the email subject._\n\n"
        "Our team will review and confirm shortly! 🖨️"
    )


def handle_awaiting_product(sender, text):
    """Handles free-text input when bot is waiting for product specification."""
    product, quantity = detect_product_and_quantity(text)
    if product:
        return confirm_catalog_order(sender, product, quantity)
    else:
        return (
            "🤔 I couldn't identify a product in your message.\n\n"
            "Please mention a product name and quantity, like:\n"
            "_'500 visiting cards'_ or _'200 flyers'_\n\n"
            "Type *Catalog* to see all available products."
        )


def parse_delivery_date(text):
    """
    Tries to understand a delivery date typed by the customer.
    Returns a clean formatted date string like "Monday, 12 May 2025"
    or None if nothing recognisable was found.

    Handles:
      - DD/MM/YYYY  or  DD-MM-YYYY  or  DD.MM.YYYY
      - "10th June", "June 10", "10 June 2025"
      - "today", "tomorrow", "next Monday" … "next Sunday"
    """
    from datetime import date as _date

    now   = datetime.now()
    today = now.date()
    text  = text.strip().lower()

    # ── Relative keywords ─────────────────────────────────────────────────────
    if text in ("today",):
        return today.strftime("%A, %d %B %Y")
    if text in ("tomorrow",):
        return (today + timedelta(days=1)).strftime("%A, %d %B %Y")

    weekdays = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    for i, day in enumerate(weekdays):
        if f"next {day}" in text or text == day:
            days_ahead = (i - today.weekday() + 7) % 7 or 7
            return (today + timedelta(days=days_ahead)).strftime("%A, %d %B %Y")

    # ── DD/MM/YYYY  DD-MM-YYYY  DD.MM.YYYY ───────────────────────────────────
    m = re.search(r'\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})\b', text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            return _date(y, mo, d).strftime("%A, %d %B %Y")
        except ValueError:
            pass

    # ── "10th June", "June 10", "10 June", "10 June 2025" ────────────────────
    months = {
        "jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,
        "apr":4,"april":4,"may":5,"jun":6,"june":6,"jul":7,"july":7,
        "aug":8,"august":8,"sep":9,"sept":9,"september":9,
        "oct":10,"october":10,"nov":11,"november":11,"dec":12,"december":12,
    }
    day_m   = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\s*(\d{4})?\b', text)
    month_d = re.search(r'\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s*(\d{4})?\b', text)

    for pattern, is_day_first in [(day_m, True), (month_d, False)]:
        if not pattern:
            continue
        g = pattern.groups()
        try:
            if is_day_first:
                d, mon_str, yr = int(g[0]), g[1], g[2]
            else:
                mon_str, d, yr = g[0], int(g[1]), g[2]
            if mon_str not in months:
                continue
            mo = months[mon_str]
            y  = int(yr) if yr else (today.year if mo >= today.month else today.year + 1)
            return _date(y, mo, d).strftime("%A, %d %B %Y")
        except (ValueError, TypeError):
            continue

    return None


def handle_awaiting_date(sender, msg_type, msg):
    """
    State: AWAITING_DATE
    Design is sent by email — so we only wait for the delivery date here.
    Accepts any text the customer types as the delivery date.
    Rejects non-text messages with a gentle reminder.
    """
    if msg_type != 'text':
        return (
            "📅 Please *type your preferred delivery date* to complete the order.\n"
            f"   _Example: 10th June, 15/06/2025, next Monday_\n\n"
            f"🎨 And don't forget to email your design to *{BUSINESS_EMAIL}*"
        )

    raw_date = msg.get('text', {}).get('body', '').strip()

    # ── Parse / validate the date the customer typed ──────────────────────────
    parsed_date = parse_delivery_date(raw_date)

    if parsed_date is None:
        # Could not understand the date — ask again politely
        return (
            "🤔 I didn't quite catch that date.\n\n"
            "Please type your delivery date clearly, for example:\n"
            "• _10th June_\n"
            "• _15/06/2025_\n"
            "• _June 15_\n"
            "• _Next Monday_"
        )

    order = user_orders.get(sender, {})
    order['delivery_date'] = parsed_date
    user_orders[sender] = order
    return finalize_order(sender)


def finalize_order(sender):
    """Finalizes the order — called once delivery date is confirmed."""
    order        = user_orders.get(sender, {})
    product      = order.get('product',          'Your product')
    quantity     = order.get('quantity',          'N/A')
    delivery     = order.get('delivery_date',     'N/A')
    placed_at    = order.get('order_placed_at', datetime.now().strftime("%d %b %Y, %I:%M %p"))

    # Reset state
    user_states[sender] = "IDLE"
    user_orders.pop(sender, None)

    return (
        "🎉 *ORDER CONFIRMED — Citizen Print*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛍️ *Product:*        {product}\n"
        f"🔢 *Quantity:*       {quantity}\n"
        f"🕒 *Order Placed:*   {placed_at}\n"
        f"📅 *Delivery Date:*  {delivery}\n"
        f"📂 *Status:*         Pending Design Review\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎨 *Next Step — Send Your Design:*\n"
        f"   📧 Email your design file to *{BUSINESS_EMAIL}*\n"
        "   ✏️ Subject: Your WhatsApp number + product name\n"
        "   _Example subject: 919876543210 — Visiting Cards_\n\n"
        "Our team will contact you for *payment & final confirmation*.\n"
        "Thank you for choosing *Citizen Print!* 🖨️"
    )


# --- 5. COMMAND REGISTRY ---
# Simple keyword → function mapping for menu-style commands
commands = {
    "hi":       lambda s: get_welcome(),
    "hello":    lambda s: get_welcome(),
    "hey":      lambda s: get_welcome(),
    "order":    lambda s: start_order_flow(s),
    "hours":    lambda s: "🕒 *Citizen Print* is open today until *8:00 PM*. See you soon!",
    "catalog":  lambda s: get_catalog(),
    "products": lambda s: get_catalog(),
    "services": lambda s: get_catalog(),
    "menu":     lambda s: get_welcome(),
    "help":     lambda s: get_welcome(),
}


# --- 6. MAIN ROUTER (Command Execution Engine) ---
def route_message(sender, msg_type, msg):
    """
    Central router — decides which function block to call based on
    the customer's current state and message content.
    """
    current_state = user_states.get(sender, "IDLE")
    text = msg.get('text', {}).get('body', '').strip() if msg_type == 'text' else ''
    text_lower = text.lower()

    # ── STATE: IDLE ──────────────────────────────────────────────────────────
    if current_state == "IDLE":

        # 1. Check exact command registry first
        if text_lower in commands:
            return commands[text_lower](sender)

        # 1b. Handle "info <product>" prefix — direct product detail lookup
        #     e.g. "info visiting cards", "info banner", "info brochures"
        if text_lower.startswith("info "):
            query = text_lower[5:].strip()
            for keyword in sorted(PRODUCT_CATALOG.keys(), key=len, reverse=True):
                if keyword in query:
                    desc = get_product_description(PRODUCT_CATALOG[keyword])
                    return desc if desc else get_catalog()
            return (
                "🤔 I couldn't find that product.\n\n"
                "Type *Catalog* to see all available products."
            )

        # 2. Detect if a product name is mentioned in the message
        product, quantity = detect_product_and_quantity(text_lower)

        # 3. Product + quantity = ORDER (check this FIRST before inquiry check)
        #    e.g. "500 visiting cards", "order 200 banners", "place order for 100 flyers"
        if product and quantity:
            return confirm_catalog_order(sender, product, quantity)

        # 4. Product mentioned + inquiry-style phrasing = INFO request
        #    e.g. "tell me about banners", "what is a brochure", "do you sell stickers"
        if product and is_product_inquiry(text_lower):
            desc = get_product_description(product)
            return desc if desc else get_catalog()

        # 5. Only a product name, no quantity, no inquiry → ask what they want
        if product:
            p = PRODUCT_DETAILS.get(product, {})
            emoji = p.get("emoji", "🖨️")
            return (
                f"{emoji} *{product}* — great choice!\n\n"
                "What would you like to do?\n\n"
                f"📋 Type *info {product.lower()}* — sizes, finish & details\n"
                f"📦 Tell us the quantity to order — e.g. _'500 {product.lower()}'_"
            )

        # 6. General inquiry, no specific product
        #    e.g. "what do you provide", "what services do you offer"
        if is_product_inquiry(text_lower):
            return get_catalog()

        # 7. Order hint but no product identified yet
        order_hints = ["order", "need", "want", "place", "buy", "print", "get"]
        if any(hint in text_lower for hint in order_hints):
            return start_order_flow(sender)

        # 8. Fallback
        return (
            "🤔 Not sure what you mean. Here's what I can do:\n\n"
            "📦 Type *Order* to start an order\n"
            "📋 Type *Catalog* to see all products\n"
            "🕒 Type *Hours* for our timings\n"
            "💬 Or just say what you need:\n"
            "   _'500 visiting cards'_ or _'200 banners'_"
        )

    # ── STATE: AWAITING_PRODUCT ──────────────────────────────────────────────
    elif current_state == "AWAITING_PRODUCT":
        if msg_type == 'text':
            return handle_awaiting_product(sender, text_lower)
        else:
            return "Please type the product name and quantity you need. _Example: 500 visiting cards_"

    # ── STATE: AWAITING_DATE ─────────────────────────────────────────────────
    elif current_state == "AWAITING_DATE":
        return handle_awaiting_date(sender, msg_type, msg)

    # ── UNKNOWN STATE (safety fallback) ──────────────────────────────────────
    else:
        user_states[sender] = "IDLE"
        return get_welcome()


# --- 7. INFRASTRUCTURE ---

async def send_whatsapp_message(recipient_id, text):
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "text",
        "text": {"body": text}
    }
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload, headers=headers)


@app.post("/webhook")
async def handle(request: Request):
    data = await request.json()
    try:
        value = data['entry'][0]['changes'][0]['value']
        if 'messages' in value:
            msg      = value['messages'][0]
            sender   = msg['from']
            msg_type = msg.get('type')

            try:
                reply = route_message(sender, msg_type, msg)
            except Exception as e:
                # Log the real error so you can see it in your terminal
                logger.exception(f"route_message crashed for sender={sender}: {e}")
                # Always send something back so the customer isn't left hanging
                reply = (
                    "⚠️ Something went wrong on our end.\n"
                    "Please try again or type *Hi* to restart."
                )

            await send_whatsapp_message(sender, reply)

    except Exception as e:
        logger.exception(f"Webhook handler error: {e}")

    return {"status": "success"}


@app.get("/webhook")
async def verify(request: Request):
    if request.query_params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(request.query_params.get("hub.challenge"))
    return "Failed"
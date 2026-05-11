import os
import httpx
from fastapi import FastAPI, Request

app = FastAPI()

# --- 1. CONFIGURATION (Paste your details here) ---
ACCESS_TOKEN = "EAAVYo9qkDuQBRZAPpzfHgpI8fefjOKSIRGmCRHPQgZCYQL4QnpR8YRDub1ZAu25VEhb3ZAI0Nese4TvO41Sq3TzzrUveH1fbJxya3uUigELmOlnOS7tZAleHmoClu9ULyPspcZBRVw1pkrqS9xbXTm2G06optkgbem1hfzQixQTCq7J4xlOtfu3Hq9eUzRnmhUcfJXWd0Uykbu1DC8RflzZAQGvyTRQYapj94JVXnwmQtOZA4qQkZBG4mYZAQfUXZAV1dWQx6m5ENZCnRnjHZAKnD0C254ZCv7"
PHONE_NUMBER_ID = "1003362262871598"
VERIFY_TOKEN = "my_cafe_bot"

# --- 2. DEFINE THE ACTION FUNCTIONS (The Logic) ---

def get_welcome():
    return (
        "👋 *Welcome to Cafe Cafine!*\n\n"
        "I'm your virtual barista. How can I help?\n"
        "👉 Type *Menu* to see treats\n"
        "👉 Type *Location* to find us\n"
        "👉 Type *Order* to start"
    )

def get_menu():
    return (
        "📜 *CAFE CAFINE MENU* 📜\n\n"
        "☕ Espresso ....... ₹120\n"
        "☕ Latte ........... ₹180\n"
        "🥐 Croissant ...... ₹90\n\n"
        "Ready? Type *Order*!"
    )

def get_location():
    return "📍 *Visit us at:*\n123 Tech Park, Phase 2, Chennai.\nOpen: 8 AM - 10 PM daily."

def get_order_info():
    return "🛒 *Ordering:* Please type the items you want (e.g., '1 Latte'). Our team will confirm via this chat!"

def get_fallback():
    return "🤔 I didn't quite get that. Try typing *Menu*, *Location*, or *Order*."

# --- 3. THE COMMAND REGISTRY (The Map) ---
# This replaces the messy if/else block
commands = {
    "hi": get_welcome,
    "hello": get_welcome,
    "hey": get_welcome,
    "start": get_welcome,
    "menu": get_menu,
    "location": get_location,
    "address": get_location,
    "order": get_order_info
}

# --- 4. THE UTILITY TO SEND MESSAGES ---
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
        response = await client.post(url, json=payload, headers=headers)
        return response.status_code

# --- 5. THE WEBHOOK ENDPOINTS ---

@app.get("/webhook")
async def verify_webhook(request: Request):
    # This is for the Meta Handshake
    params = request.query_params
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Verification token mismatch"

@app.post("/webhook")
async def handle_messages(request: Request):
    data = await request.json()
    try:
        # Check if it's a message event
        if 'messages' in data['entry'][0]['changes'][0]['value']:
            message = data['entry'][0]['changes'][0]['value']['messages'][0]
            sender_id = message['from']
            user_input = message.get('text', {}).get('body', '').lower().strip()

            # --- THE COMMAND PATTERN EXECUTION ---
            # Lookup function in dictionary, default to fallback
            action = commands.get(user_input, get_fallback)
            
            # Execute the function to get the response string
            reply_text = action()

            # Send the reply
            await send_whatsapp_message(sender_id, reply_text)
            print(f"✅ Sent response to {sender_id}")

    except Exception as e:
        print(f"❌ Error: {e}")
    
    return {"status": "success"}
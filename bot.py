import requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

PAGE_ACCESS_TOKEN = "EAAVYo9qkDuQBRaqaUZBlYpZArmz08MUK8HPnHGfhZC6aUPWgQnhZCMqLBmZBBBetlMEkiUfgKxH4fmZCCmwsgUNMetDjHmO7nFquRuhh5Q7tIBMUGhe3suyFtz6beUJbjkJXJNLLXKfKVG81lNvV2iVoWiZCA8MiMhpe7Pk7TstnhV9ZAk4oeyZBpStQkJdDVZBSq9dEePekxXmQZDZD"
VERIFY_TOKEN = "my_cafe_bot" 

app = FastAPI()
@app.get("/webhook")
async def verify(request: Request):
    challenge = request.query_params.get("hub.challenge")
    verify_token = request.query_params.get("hub.verify_token")

    if verify_token == VERIFY_TOKEN:
        return PlainTextResponse(content=challenge)
    return PlainTextResponse(content="Verification failed", status_code=403)

# --- MESSAGE HANDLING (The "Brain") ---
@app.post("/webhook")
async def handle_message(request: Request):
    data = await request.json()
    try:
        # Check if this is a message from a user
        if data['object'] == 'page':
            for entry in data['entry']:
                for messaging_event in entry['messaging']:
                    if messaging_event.get('message'):
                        sender_id = messaging_event['sender']['id']
                        user_text = messaging_event['message'].get('text', '').lower()

                        # Bot Logic: What should the bot say?
                        if "hi" in user_text or "hello" in user_text:
                            reply = "Hello! ☕ Welcome to Cafe Cafine. Type 'Menu' to see our food or 'Help' for assistance."
                        elif "menu" in user_text:
                            reply = "Today's Menu: \n1. Cold Brew Coffee 🧊\n2. Chocolate Croissant 🥐\n3. Blueberry Muffin 🧁"
                        elif "help" in user_text:
                            reply = "I'm your Cafe Assistant! You can ask for the 'Menu' or our 'Location'."
                        else:
                            reply = "I'm still learning! Try saying 'Hi' or 'Menu'."

                        # Send the reply back to Facebook
                        send_fb_message(sender_id, reply)
    except Exception as e:
        print(f"Error: {e}")
    
    return {"status": "ok"}

def send_fb_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    requests.post(url, json=payload)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
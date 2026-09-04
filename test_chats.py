import os
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

chat_ids = [cid.strip() for cid in CHAT_ID.split(",") if cid.strip()]
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

for chat_id in chat_ids:
    print(f"\nTesting chat_id: {chat_id}")
    resp = requests.post(url, data={"chat_id": chat_id, "text": "Test message"})
    print(f"  Status: {resp.status_code}")
    print(f"  Response: {resp.text}")
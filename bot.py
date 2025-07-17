"""Flask webhook server handling Telegram updates."""
from __future__ import annotations

import os
from typing import Any, Dict

from flask import Flask, request, abort
import requests


from ai import handle_message
from db import init_db

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

init_db()
app = Flask(__name__)


@app.route("/telegram", methods=["POST"])
def telegram_webhook() -> Dict[str, Any]:
    """Process incoming Telegram webhook calls."""
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        abort(403)

    data = request.get_json(force=True)
    message = data.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "")

    if chat_id is None:
        return {}

    reply = handle_message(chat_id, text)

    payload = {"chat_id": chat_id, "text": reply}
    requests.post(TELEGRAM_API_URL, json=payload)

    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

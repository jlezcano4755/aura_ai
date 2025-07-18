"""Flask webhook server handling Telegram updates."""
from __future__ import annotations

import os
import logging
from typing import Any, Dict

from flask import Flask, request, abort
import requests


from ai import handle_message
from db import init_db, get_lead_by_telegram_id, create_lead, update_lead

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s:%(name)s: %(message)s",
    filename="server.log",
    filemode="a",
)
logger = logging.getLogger(__name__)

init_db()
app = Flask(__name__)


@app.route("/telegram", methods=["POST"])
def telegram_webhook() -> Dict[str, Any]:
    """Process incoming Telegram webhook calls."""
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        abort(403)

    data = request.get_json(force=True)
    logger.debug(f"update received: {data}")
    message = data.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")  # where replies are sent
    user = message.get("from", {})
    telegram_id = user.get("id")
    text = message.get("text", "")
    contact = message.get("contact")

    if chat_id is None or telegram_id is None:
        return {}

    create_lead(telegram_id)

    if contact:
        update_lead(
            telegram_id,
            phone=contact.get("phone_number"),
            name=contact.get("first_name"),
        )

    lead = get_lead_by_telegram_id(telegram_id)

    if (lead is None or lead[5] is None) and not contact:
        keyboard = {
            "keyboard": [[{"text": "Compartir tu contacto.", "request_contact": True}]],
            "one_time_keyboard": True,
        }
        payload = {
            "chat_id": chat_id,
            "text": "Por favor comparte tu n\u00famero de tel\u00e9fono.",
            "reply_markup": keyboard,
        }
        requests.post(TELEGRAM_API_URL, json=payload)
        logger.debug(f"requested contact from {chat_id}")
        return {"ok": True}

    reply = handle_message(telegram_id, text)

    payload = {"chat_id": chat_id, "text": reply}
    requests.post(TELEGRAM_API_URL, json=payload)
    logger.debug(f"sent reply to {chat_id}: {reply}")

    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

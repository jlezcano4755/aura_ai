"""GPT-based conversation logic for the AURA assistant."""
from __future__ import annotations

import json
import os
from typing import Dict, List

from openai import OpenAI

from db import get_lead_by_telegram_id, save_lead


SYSTEM_PROMPT = (
    "You are AURA, a polite assistant helping new psychology clients schedule an appointment. "
    "Gather the client's full name, requested service type, preferred time, and phone number. "
    "Once all details are collected, confirm and end the conversation."
)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

# In-memory session store
active_sessions: Dict[int, List[Dict[str, str]]] = {}


def start_session(chat_id: int) -> None:
    """Initialize conversation history for a Telegram chat."""
    if chat_id not in active_sessions:
        active_sessions[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]


def handle_message(chat_id: int, text: str) -> str:
    """Process an incoming message and return the assistant's reply."""
    if get_lead_by_telegram_id(chat_id):
        return "Thank you, we already have your information. We'll be in touch soon."

    start_session(chat_id)
    msgs = active_sessions[chat_id]
    msgs.append({"role": "user", "content": text})

    tools = [
        {
            "type": "function",
            "function": {
                "name": "save_lead",
                "description": "Store prospect data once all fields are collected",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "service": {"type": "string"},
                        "preferred_time": {"type": "string"},
                        "phone": {"type": "string"},
                    },
                    "required": ["name", "service", "preferred_time", "phone"],
                },
            },
        }
    ]

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=msgs,
        tools=tools,
        tool_choice="auto",
    )

    message = response.choices[0].message
    msgs.append(message.model_dump(exclude_none=True))

    if message.tool_calls:
        for call in message.tool_calls:
            if call.function.name == "save_lead":
                args = json.loads(call.function.arguments)
                save_lead(
                    telegram_id=chat_id,
                    name=args["name"],
                    service=args["service"],
                    preferred_time=args["preferred_time"],
                    phone=args["phone"],
                )
                msgs.append({"role": "assistant", "content": "Thank you! We'll reach out soon."})
                return "Thank you! We'll reach out soon."

    return message.content or ""


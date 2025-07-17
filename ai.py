"""GPT-based conversation logic for the AURA assistant."""
from __future__ import annotations

import os
from typing import Dict

import openai

from db import save_lead

# System prompt guiding the assistant's tone and purpose
SYSTEM_PROMPT = (
    "You are AURA, a polite human-like assistant helping new clients "
    "schedule an appointment with a psychologist. "
    "Collect the client's name, the service type they need, and their "
    "preferred time. Once you have all of the information, politely "
    "confirm and let them know someone will reach out at +50766554337."
)

openai.api_key = os.environ.get("OPENAI_API_KEY", "")

# In-memory session store
active_sessions: Dict[int, Dict] = {}

PROMPTS = {
    0: "Ask the user for their name.",
    1: "Thank them and ask what service they are interested in.",
    2: "Thank them and ask for their preferred schedule.",
    3: "Confirm the provided name, service, and preferred schedule. "
       "Tell them someone will contact them at +50766554337 and end the conversation politely."
}


def start_session(chat_id: int) -> None:
    """Create a new session for a Telegram chat."""
    if chat_id not in active_sessions:
        active_sessions[chat_id] = {
            "step": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
            ],
            "data": {
                "name": None,
                "service": None,
                "preferred_time": None,
            },
        }


def handle_message(chat_id: int, text: str) -> str:
    """Process an incoming message and return the assistant's reply."""
    session = active_sessions.setdefault(chat_id, None)
    if session is None:
        start_session(chat_id)
        session = active_sessions[chat_id]

    step = session["step"]

    if step == 0:
        session["data"]["name"] = text.strip()
        session["step"] = 1
    elif step == 1:
        session["data"]["service"] = text.strip()
        session["step"] = 2
    elif step == 2:
        session["data"]["preferred_time"] = text.strip()
        save_lead(
            telegram_id=chat_id,
            name=session["data"]["name"],
            service=session["data"]["service"],
            preferred_time=session["data"]["preferred_time"],
        )
        session["step"] = 3

    instruction = PROMPTS.get(session["step"], "")
    session["messages"].append({"role": "system", "content": instruction})

    response = openai.ChatCompletion.create(
        model="gpt-4.1",
        messages=session["messages"],
    )

    reply = response.choices[0].message.content.strip()
    session["messages"].append({"role": "assistant", "content": reply})
    return reply

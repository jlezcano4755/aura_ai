"""GPT-based conversation logic for the AURA assistant."""
from __future__ import annotations

import json
import os
from typing import Dict, List

from openai import OpenAI

from datetime import datetime

from db import (
    get_lead_by_telegram_id,
    create_lead,
    update_lead,
    list_services,
    list_open_times,
    schedule_appointment,
    update_sale_temperature,
    get_lead_id,
)


SYSTEM_PROMPT = (

    "Eres AURA, la asistente virtual de la psicóloga Clara, especializada en neurociencia conductual y desarrollo infantil. "
    "Clara ofrece varios paquetes de terapia y servicios relacionados y trabaja de lunes a sábado de 2:00 PM a 10:00 PM. "
    "Habla siempre en español a menos que detectes que el usuario escribe claramente en otro idioma. "
    "Conversar brevemente para comprender las necesidades antes de ofrecer precios detallados. "
    "Ayuda a agendar sesiones, responde preguntas sobre la práctica de Clara y mantén las respuestas cortas y amables. "
    "Reúne el nombre del cliente, servicio de interés, horario preferido y número de teléfono, actualizando la base de datos a medida que aprendas nuevos datos."

)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4.1")

# In-memory session store
active_sessions: Dict[int, List[Dict[str, str]]] = {}


def start_session(telegram_id: int) -> None:
    """Initialize conversation history for a Telegram user."""
    now = datetime.utcnow().isoformat(sep=" ", timespec="minutes")
    services = ", ".join([f"{s[1]} (${s[2]})" for s in list_services()])
    open_times = ", ".join([
        f"{ot[0]}:{ot[1]}-{ot[2]}" for ot in list_open_times()
    ])
    lead = get_lead_by_telegram_id(telegram_id)
    lead_info_parts = []
    if lead:
        if lead[2]:
            lead_info_parts.append(f"name: {lead[2]}")
        if lead[3]:
            lead_info_parts.append(f"service: {lead[3]}")
        if lead[4]:
            lead_info_parts.append(f"preferred time: {lead[4]}")
        if lead[5]:
            lead_info_parts.append(f"phone: {lead[5]}")
    lead_info = " Known lead data: " + ", ".join(lead_info_parts) + "." if lead_info_parts else ""
    system_msg = (
        f"{SYSTEM_PROMPT} Current datetime: {now}. Available services: {services}. "
        f"Opening hours (day:open-close): {open_times}.{lead_info}"
    )
    if telegram_id in active_sessions:
        active_sessions[telegram_id][0] = {"role": "system", "content": system_msg}
    else:
        active_sessions[telegram_id] = [{"role": "system", "content": system_msg}]


def handle_message(telegram_id: int, text: str) -> str:
    """Process an incoming message and return the assistant's reply."""
    create_lead(telegram_id)

    start_session(telegram_id)
    msgs = active_sessions[telegram_id]
    msgs.append({"role": "user", "content": text})

    tools = [
        {
            "type": "function",
            "function": {
                "name": "update_lead",
                "description": "Update lead information as soon as it is known",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "service": {"type": "string"},
                        "preferred_time": {"type": "string"},
                        "phone": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "schedule_appointment",
                "description": "Schedule a session for the lead",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {"type": "integer"},
                        "scheduled_time": {"type": "string"},
                    },
                    "required": ["service_id", "scheduled_time"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_sale_temperature",
                "description": "Update the lead's sale temperature (0-100)",
                "parameters": {
                    "type": "object",
                    "properties": {"temperature": {"type": "integer"}},
                    "required": ["temperature"],
                },
            },
        },
    ]

    loop_count = 0
    while True:
        response = client.chat.completions.create(
            model=model,
            messages=msgs,
            tools=tools,
            tool_choice="auto",
        )

        message = response.choices[0].message
        msgs.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            return message.content or ""

        tool_messages = []
        for call in message.tool_calls:
            result = None
            if call.function.name == "update_lead":
                args = json.loads(call.function.arguments)
                update_lead(telegram_id, **args)
                result = "ok"
            elif call.function.name == "schedule_appointment":
                args = json.loads(call.function.arguments)
                lead_id = get_lead_id(telegram_id)
                success = False
                if lead_id:
                    success = schedule_appointment(
                        lead_id=lead_id,
                        service_id=args["service_id"],
                        scheduled_time=args["scheduled_time"],
                    )
                result = str(success).lower()
            elif call.function.name == "update_sale_temperature":
                args = json.loads(call.function.arguments)
                update_sale_temperature(telegram_id, int(args["temperature"]))
                result = "ok"

            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.function.name,
                    "content": json.dumps({"result": result}),
                }
            )

        msgs.extend(tool_messages)
        loop_count += 1
        if loop_count > 3:
            return ""

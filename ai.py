"""GPT-based conversation logic for the AURA assistant."""
from __future__ import annotations

import json
import os
from typing import Dict, List

from openai import OpenAI

from datetime import datetime, timedelta

from db import (
    get_lead_by_telegram_id,
    create_lead,
    update_lead,
    list_services,
    list_open_times,
    schedule_appointment,
    update_sale_temperature,
    get_lead_id,
    check_availability,
    suggest_alternative_slots,
    add_intake_note,
    escalate_case,
)


SYSTEM_PROMPT = (
    "Eres AURA, asistente virtual de la Lic. Clara Ordoñez, psicóloga especializada en neurociencia conductual y desarrollo infantil. "
    "Hablas en español salvo que el usuario solicite otro idioma y mantienes un tono cálido, empático, conciso y profesional. "
    "Evalúa de forma rápida la situación emocional, brinda contención sin diagnosticar, y reúne nombre, servicio de interés, horario preferido y teléfono. "
    "Antes de ofrecer un horario verifica disponibilidad y, de ser necesario, sugiere alternativas; después agenda sin solapamientos. "
    "Escala urgencias o peticiones de hablar con Clara y registra la temperatura de venta según el interés mostrado. "
    "Clara atiende de lunes a sábado entre las 14:00 y las 22:00."
)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4.1")

# In-memory session store
active_sessions: Dict[int, List[Dict[str, str]]] = {}
# Tracks if a conversation has been escalated due to emergency.
escalated_flags: Dict[int, bool] = {}

# Time zone offset for the user (UTC-5)
USER_TZ_OFFSET = timedelta(hours=-5)


def start_session(telegram_id: int) -> None:
    """Initialize conversation history for a Telegram user."""
    now = (datetime.utcnow() + USER_TZ_OFFSET).isoformat(sep=" ", timespec="minutes")
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
        f"{SYSTEM_PROMPT} Current datetime (UTC-05:00): {now}. Available services: {services}. "
        f"Opening hours (day:open-close): {open_times}.{lead_info}"
    )
    if telegram_id in active_sessions:
        active_sessions[telegram_id][0] = {"role": "system", "content": system_msg}
    else:
        active_sessions[telegram_id] = [{"role": "system", "content": system_msg}]
        escalated_flags[telegram_id] = False


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
        {
            "type": "function",
            "function": {
                "name": "check_availability",
                "description": "Check if a time slot is free for a service",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {"type": "integer"},
                        "proposed_time": {"type": "string"},
                    },
                    "required": ["service_id", "proposed_time"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "suggest_alternative_slots",
                "description": "Suggest up to 3 alternative slots",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {"type": "integer"},
                        "date_range": {"type": "string"},
                    },
                    "required": ["service_id", "date_range"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_intake_note",
                "description": "Store an intake note for the lead",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "note_type": {"type": "string"},
                        "note_text": {"type": "string"},
                    },
                    "required": ["note_type", "note_text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "escalate_case",
                "description": "Escalate the conversation to Clara",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string"},
                        "details": {"type": "string"},
                    },
                    "required": ["reason"],
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
                # raise sale temperature when we learn key info
                if any(k in args for k in ("service", "preferred_time")):
                    update_sale_temperature(telegram_id, 70)
                elif "name" in args and args["name"] and len(args["name"]) > 1:
                    update_sale_temperature(telegram_id, 30)
                result = "ok"
            elif call.function.name == "schedule_appointment":
                args = json.loads(call.function.arguments)
                if escalated_flags.get(telegram_id):
                    success = False
                else:
                    lead_id = get_lead_id(telegram_id)
                    success = False
                    if lead_id:
                        success = schedule_appointment(
                            lead_id=lead_id,
                            service_id=args["service_id"],
                            scheduled_time=args["scheduled_time"],
                        )
                        if success:
                            # store service and time and raise temperature
                            from db import get_service_name
                            service_name = get_service_name(args["service_id"])
                            update_lead(
                                telegram_id,
                                service=service_name,
                                preferred_time=args["scheduled_time"],
                            )
                            update_sale_temperature(telegram_id, 100)
                result = str(success).lower()
            elif call.function.name == "update_sale_temperature":
                args = json.loads(call.function.arguments)
                update_sale_temperature(telegram_id, int(args["temperature"]))
                result = "ok"
            elif call.function.name == "check_availability":
                args = json.loads(call.function.arguments)
                if escalated_flags.get(telegram_id):
                    available = False
                else:
                    available = check_availability(
                        args["service_id"], args["proposed_time"]
                    )
                result = {"available": available}
            elif call.function.name == "suggest_alternative_slots":
                args = json.loads(call.function.arguments)
                slots = suggest_alternative_slots(
                    args["service_id"], args["date_range"]
                )
                result = {"slots": slots}
            elif call.function.name == "add_intake_note":
                args = json.loads(call.function.arguments)
                lead_id = get_lead_id(telegram_id)
                if lead_id:
                    add_intake_note(
                        lead_id=lead_id,
                        note_type=args["note_type"],
                        note_text=args["note_text"],
                    )
                result = "ok"
            elif call.function.name == "escalate_case":
                args = json.loads(call.function.arguments)
                lead_id = get_lead_id(telegram_id)
                escalated_flags[telegram_id] = True
                if lead_id:
                    escalate_case(
                        lead_id=lead_id,
                        reason=args["reason"],
                        details=args.get("details"),
                    )
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

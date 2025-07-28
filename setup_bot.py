"""Bootstrap deployment from a YAML configuration."""

import re
import sys
from pathlib import Path
from typing import Any, Dict

import requests
import yaml
from telethon import TelegramClient
from pyngrok import ngrok
import asyncio

from db import init_db, seed_services, seed_open_times


async def create_telegram_bot(config: Dict[str, Any]) -> str:
    """Interact with BotFather to create a bot and return its token."""
    api_id = int(config["telegram_api_id"])
    api_hash = config["telegram_api_hash"]
    phone = config["telegram_phone"]
    name = config["bot_name"]
    username = config["bot_username"]

    client = TelegramClient("bot_setup", api_id, api_hash)
    await client.start(phone=phone)

    async with client.conversation("BotFather") as conv:
        await conv.send_message("/newbot")
        await conv.get_response()
        await conv.send_message(name)
        await conv.get_response()
        await conv.send_message(username)
        final = await conv.get_response()
    await client.disconnect()

    match = re.search(r"(\d+:[A-Za-z0-9_-]+)", final.text)
    if not match:
        raise RuntimeError("Failed to obtain bot token from BotFather")
    return match.group(1)


async def customise_bot(config: Dict[str, Any], bot_token: str) -> None:
    """Set description and about text for the bot if provided."""
    api_id = int(config["telegram_api_id"])
    api_hash = config["telegram_api_hash"]
    phone = config["telegram_phone"]
    username = config["bot_username"]
    description = config.get("bot_description")
    about = config.get("bot_about")

    client = TelegramClient("bot_setup", api_id, api_hash)
    await client.start(phone=phone)
    async with client.conversation("BotFather") as conv:
        if description:
            await conv.send_message("/setdescription")
            await conv.get_response()
            await conv.send_message(username)
            await conv.get_response()
            await conv.send_message(description)
            await conv.get_response()

        if about:
            await conv.send_message("/setabouttext")
            await conv.get_response()
            await conv.send_message(username)
            await conv.get_response()
            await conv.send_message(about)
            await conv.get_response()
    await client.disconnect()


def register_webhook(bot_token: str, url: str, secret: str) -> None:
    """Configure the Telegram webhook."""
    resp = requests.post(
        f"https://api.telegram.org/bot{bot_token}/setWebhook",
        data={"url": url, "secret_token": secret},
        timeout=30,
    )
    resp.raise_for_status()


def start_ngrok(port: int, authtoken: str | None = None) -> str:
    """Start an ngrok tunnel and return the public URL."""
    if authtoken:
        ngrok.set_auth_token(authtoken)
    tunnel = ngrok.connect(port, bind_tls=True)
    return tunnel.public_url


REQUIRED_KEYS = [
    "openai_api_key",
    "telegram_api_id",
    "telegram_api_hash",
    "telegram_phone",
    "bot_name",
    "bot_username",
    "telegram_webhook_secret",
]


def write_env(config: dict, bot_token: str, webhook_url: str) -> None:
    """Generate .env.local with the bot token and webhook settings."""
    env_lines = []
    for key in [
        "openai_api_key",
        "openai_chat_model",
        "openai_vector_store_id",
        "openai_tts_model",
    ]:
        value = config.get(key)
        if value is not None:
            env_lines.append(f"{key.upper()}={value}")
    env_lines.append(f"TELEGRAM_BOT_TOKEN={bot_token}")
    env_lines.append(f"TELEGRAM_WEBHOOK_SECRET={config['telegram_webhook_secret']}")
    env_lines.append(f"TELEGRAM_WEBHOOK_URL={webhook_url}")
    Path(".env.local").write_text("\n".join(env_lines) + "\n")


def seed_db(config: dict) -> None:
    if Path("crm.db").exists():
        Path("crm.db").unlink()
    init_db()
    services = config.get("services")
    if services:
        seed_services([(s["name"], float(s["price"])) for s in services])
    times = config.get("open_times")
    if times:
        seed_open_times(
            [
                (int(t["day"]), t["open"], t["close"])  # type: ignore
                for t in times
            ]
        )


def main(path: str) -> None:
    config = yaml.safe_load(Path(path).read_text())
    missing = [k for k in REQUIRED_KEYS if k not in config]
    if missing:
        raise SystemExit(f"Missing required keys: {', '.join(missing)}")

    bot_token = asyncio.run(create_telegram_bot(config))
    asyncio.run(customise_bot(config, bot_token))

    webhook_url = config.get("telegram_webhook_url")
    if not webhook_url:
        port = int(config.get("local_port", 8000))
        ngrok_token = config.get("ngrok_authtoken")
        public = start_ngrok(port, ngrok_token)
        webhook_url = f"{public}/telegram"
    register_webhook(bot_token, webhook_url, config["telegram_webhook_secret"])
    write_env(config, bot_token, webhook_url)
    seed_db(config)
    if not config.get("telegram_webhook_url"):
        print(f"ngrok tunnel started: {webhook_url}")
    print("Bot created and deployment files generated: .env.local and crm.db")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python setup_bot.py <config.yml>")
        raise SystemExit(1)
    main(sys.argv[1])

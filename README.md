# AURA MVP

AURA (Automated Unified Response Agent) is an AI-powered Telegram assistant for solo professionals. This MVP focuses on psychologists who want to automate client intake through Telegram.

## Files
- `bot.py` – Flask server exposing the `/telegram` webhook. Handles Telegram updates and sends replies.
- `ai.py` – Conversation logic using OpenAI's chat completions API and in-memory session management.
- `db.py` – SQLite schema and helper to store collected leads.
- `.env` – Example environment variable file.
- `crm.db` – SQLite database created at runtime.

## Setup
1. Install dependencies (requires `openai` version 1.97.0):
   ```bash
   pip install flask requests openai==1.97.0
   ```
2. Copy `.env` and fill in your keys:
   ```bash
   cp .env .env.local
   # edit .env.local with OPENAI_API_KEY, TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET
   ```
3. Run the server:
   ```bash
   python bot.py
   ```
4. Configure your Telegram bot webhook to point to `https://<your-domain>/telegram` using the secret token from `TELEGRAM_WEBHOOK_SECRET`.

The bot converses with prospects, collects their name, service type, preferred schedule and phone number, then stores the information in `crm.db`.


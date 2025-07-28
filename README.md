# AURA MVP

AURA (Automated Unified Response Agent) is an AI-powered Telegram assistant for solo professionals. This MVP focuses on psychologists who want to automate client intake through Telegram.

## Files
- `bot.py` – Flask server exposing the `/telegram` webhook. Handles Telegram updates and sends replies.

- `ai.py` – Conversation logic using OpenAI's chat completions API and in-memory session management.
- `db.py` – SQLite schema and helper to store collected leads.
- `.env` – Example environment variable file.
- `crm.db` – SQLite database created at runtime.

## Setup
1. **Create a Telegram bot**
   1. Open a chat with [@BotFather](https://t.me/BotFather) in Telegram.
   2. Send `/newbot` and follow the prompts to choose a name and username.
   3. BotFather will return a token – copy it and set it as `TELEGRAM_BOT_TOKEN`.
   4. (Optional) Use `/setdescription` and `/setabouttext` to customise your bot.
2. *(For automated setup)* Create Telegram API credentials by logging in to [my.telegram.org](https://my.telegram.org) and generating an **API ID** and **API hash**.
3. Install dependencies (requires `openai` version 1.97.0):
   ```bash
   pip install flask requests openai==1.97.0
   ```
4. Copy `.env` and fill in your keys:
   ```bash
   cp .env .env.local
   # edit .env.local with OPENAI_API_KEY, TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET
   ```
5. Run the server:
    ```bash
    python bot.py
    ```
6. Expose the server publicly (e.g. via a domain or with ngrok) and configure the Telegram webhook:
   ```bash
   curl -X POST https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook \
        -d "url=https://<your-domain>/telegram&secret_token=$TELEGRAM_WEBHOOK_SECRET"
   ```

The bot converses with prospects, collects their name, service type, preferred schedule and phone number, then stores the information in `crm.db`.

`db.py` seeds a few sample services and opening hours for Clara's practice on the first run. Leads are stored using the user's Telegram ID (not the chat ID) so conversation history and appointments are tied to each person.

## Automated deployment
To bootstrap the bot configuration from a single YAML file, install the extra dependencies and run `setup_bot.py`:

```bash
pip install pyyaml python-dotenv telethon requests
python setup_bot.py example_config.yml
```

The YAML must contain your Telegram API credentials (`telegram_api_id`, `telegram_api_hash` and `telegram_phone`) and bot details (`bot_name`, `bot_username`, `telegram_webhook_url`, `telegram_webhook_secret`). OpenAI keys are also required but are not generated automatically. Optional `services` and `open_times` entries seed the database. See `example_config.yml` for the full format. When run, the script will create the bot via BotFather, register the webhook and write `.env.local` and `crm.db`.

import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path('crm.db')


def init_db() -> None:
    """Initialize the leads table if it does not exist."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                name TEXT,
                service TEXT,
                preferred_time TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def save_lead(telegram_id: int, name: str, service: str, preferred_time: str) -> None:
    """Save a collected lead into the database."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO leads(telegram_id, name, service, preferred_time) VALUES (?,?,?,?)",
            (telegram_id, name, service, preferred_time),
        )
        conn.commit()


# Ensure the database exists when this module is imported
init_db()

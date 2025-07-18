import sqlite3
from contextlib import closing
from pathlib import Path


DB_PATH = Path("crm.db")


def init_db() -> None:
    """Initialize database tables."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                name TEXT,
                service TEXT,
                preferred_time TEXT,
                phone TEXT,
                sale_temperature INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS open_times (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day_of_week INTEGER,
                open_time TEXT,
                close_time TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER,
                service_id INTEGER,
                scheduled_time TEXT
            )
            """
        )
        conn.commit()

        # Seed default data if tables are empty
        cur = conn.execute("SELECT COUNT(*) FROM services")
        if cur.fetchone()[0] == 0:
            services = [
                ("Initial consultation", 50.0),
                ("Behavioral therapy package", 300.0),
                ("Parent guidance session", 80.0),
            ]
            conn.executemany(
                "INSERT INTO services(name, price) VALUES (?, ?)", services
            )

        cur = conn.execute("SELECT COUNT(*) FROM open_times")
        if cur.fetchone()[0] == 0:
            times = [
                (d, "14:00", "22:00") for d in range(1, 7)
            ]  # Monday(1) to Saturday(6)
            conn.executemany(
                "INSERT INTO open_times(day_of_week, open_time, close_time) VALUES (?,?,?)",
                times,
            )

        conn.commit()


def create_lead(telegram_id: int) -> None:
    """Ensure a lead entry exists."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO leads(telegram_id) VALUES (?)",
            (telegram_id,),
        )
        conn.commit()


def update_lead(telegram_id: int, **fields) -> None:
    """Update given fields for a lead."""
    if not fields:
        return
    columns = ", ".join([f"{k}=?" for k in fields.keys()])
    values = list(fields.values())
    values.append(telegram_id)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            f"UPDATE leads SET {columns} WHERE telegram_id=?",
            values,
        )
        conn.commit()

        
def get_lead_by_telegram_id(telegram_id: int):
    """Return a lead row if it exists for a Telegram ID."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            "SELECT * FROM leads WHERE telegram_id=?",
            (telegram_id,),
        )
        return cur.fetchone()


def get_lead_id(telegram_id: int) -> int | None:
    """Return the internal lead id for a telegram user."""
    row = get_lead_by_telegram_id(telegram_id)
    return row[0] if row else None


def list_services():
    """Return all services with pricing."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute("SELECT id, name, price FROM services")
        return cur.fetchall()


def list_open_times():
    """Return weekly open times."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute("SELECT day_of_week, open_time, close_time FROM open_times")
        return cur.fetchall()


def schedule_appointment(lead_id: int, service_id: int, scheduled_time: str) -> None:
    """Store a new appointment if the slot is free."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE scheduled_time=?",
            (scheduled_time,),
        )
        if cur.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO appointments(lead_id, service_id, scheduled_time) VALUES (?,?,?)",
                (lead_id, service_id, scheduled_time),
            )
            conn.commit()


def update_sale_temperature(telegram_id: int, temperature: int) -> None:
    """Update a lead's sale temperature."""
    update_lead(telegram_id, sale_temperature=temperature)

      
# Ensure the database exists when this module is imported
init_db()

import sqlite3
from contextlib import closing
from pathlib import Path
from datetime import datetime, timedelta


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS intake_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER,
                note_type TEXT,
                note_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS escalated_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER,
                reason TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


def get_service_name(service_id: int) -> str | None:
    """Return the service name for a given id."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            "SELECT name FROM services WHERE id=?",
            (service_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def list_open_times():
    """Return weekly open times."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute("SELECT day_of_week, open_time, close_time FROM open_times")
        return cur.fetchall()


def _is_within_open_times(conn: sqlite3.Connection, when: datetime) -> bool:
    day = when.isoweekday()
    cur = conn.execute(
        "SELECT open_time, close_time FROM open_times WHERE day_of_week=?",
        (day,),
    )
    row = cur.fetchone()
    if not row:
        return False
    open_t = datetime.strptime(row[0], "%H:%M").time()
    close_t = datetime.strptime(row[1], "%H:%M").time()
    return open_t <= when.time() <= close_t


def schedule_appointment(lead_id: int, service_id: int, scheduled_time: str) -> bool:
    """Store a new appointment if the slot is free and within open hours."""
    when = datetime.fromisoformat(scheduled_time)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        if not _is_within_open_times(conn, when):
            return False
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
            return True
    return False


def update_sale_temperature(telegram_id: int, temperature: int) -> None:
    """Update a lead's sale temperature."""
    update_lead(telegram_id, sale_temperature=temperature)


def check_availability(service_id: int, proposed_time: str) -> bool:
    """Return True if the slot is free and within opening hours."""
    when = datetime.fromisoformat(proposed_time)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        if not _is_within_open_times(conn, when):
            return False
        cur = conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE scheduled_time=?",
            (proposed_time,),
        )
        return cur.fetchone()[0] == 0


def suggest_alternative_slots(service_id: int, date_range: str) -> list[str]:
    """Return up to 3 free slots within the given date range."""
    start_str, end_str = date_range.split("/")
    start = datetime.fromisoformat(start_str)
    end = datetime.fromisoformat(end_str)
    slots: list[str] = []
    with closing(sqlite3.connect(DB_PATH)) as conn:
        current = start
        while current <= end and len(slots) < 3:
            if _is_within_open_times(conn, current):
                cur = conn.execute(
                    "SELECT COUNT(*) FROM appointments WHERE scheduled_time=?",
                    (current.isoformat(timespec='minutes'),),
                )
                if cur.fetchone()[0] == 0:
                    slots.append(current.isoformat(timespec='minutes'))
            current += timedelta(hours=1)
    return slots


def add_intake_note(lead_id: int, note_type: str, note_text: str) -> None:
    """Store an intake note for a lead."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO intake_notes(lead_id, note_type, note_text) VALUES (?,?,?)",
            (lead_id, note_type, note_text),
        )
        conn.commit()


def escalate_case(lead_id: int, reason: str, details: str | None = None) -> None:
    """Record an escalated case for manual follow-up."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO escalated_cases(lead_id, reason, details) VALUES (?,?,?)",
            (lead_id, reason, details or ""),
        )
        conn.commit()


def seed_services(services: list[tuple[str, float]]) -> None:
    """Replace the services table with the given list."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute("DELETE FROM services")
        conn.executemany(
            "INSERT INTO services(name, price) VALUES (?, ?)", services
        )
        conn.commit()


def seed_open_times(times: list[tuple[int, str, str]]) -> None:
    """Replace opening hours with the given schedule."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute("DELETE FROM open_times")
        conn.executemany(
            "INSERT INTO open_times(day_of_week, open_time, close_time) VALUES (?,?,?)",
            times,
        )
        conn.commit()

      
# Ensure the database exists when this module is imported
init_db()

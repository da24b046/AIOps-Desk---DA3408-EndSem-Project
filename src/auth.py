"""Local account storage and password verification."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from pwdlib import PasswordHash

DATABASE = Path(__file__).resolve().parents[1] / "state/app/aiops.db"
PASSWORD_HASH = PasswordHash.recommended()
ROLES = {"viewer", "operator", "maintainer"}


def initialize_users():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DATABASE, timeout=3)) as database:
        database.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL
                    CHECK(role IN ('viewer', 'operator', 'maintainer')),
                created_at TEXT NOT NULL
            )
        """)
        database.commit()


def get_user(username):
    with closing(sqlite3.connect(DATABASE, timeout=3)) as database:
        database.row_factory = sqlite3.Row
        row = database.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def create_user(username, password, role):
    if role not in ROLES:
        raise ValueError("Unknown role.")
    if len(password) < 10:
        raise ValueError("Use a password with at least 10 characters.")

    encoded = PASSWORD_HASH.hash(password)

    with closing(sqlite3.connect(DATABASE, timeout=3)) as database:
        with database:
            database.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?)",
                (
                    username,
                    encoded,
                    role,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )


def verify_user(username, password):
    user = get_user(username)
    if not user:
        return None
    if not PASSWORD_HASH.verify(password, user["password_hash"]):
        return None
    return {"username": user["username"], "role": user["role"]}

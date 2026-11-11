"""Local bearer sessions with hashed tokens and one-hour expiry."""

import hashlib
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, SecretStr

from src.auth import DATABASE, initialize_users, verify_user

router = APIRouter(prefix="/v1", tags=["Sessions"])
bearer = HTTPBearer(auto_error=False)


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=1024)


def token_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def initialize_sessions():
    initialize_users()
    with closing(sqlite3.connect(DATABASE, timeout=3)) as database:
        database.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL REFERENCES users(username),
                expires_at INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        database.commit()


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    unauthorized = HTTPException(
        status_code=401,
        detail="Valid login required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    with closing(sqlite3.connect(DATABASE, timeout=3)) as database:
        row = database.execute(
            """
            SELECT users.username, users.role
            FROM sessions
            JOIN users ON users.username = sessions.username
            WHERE sessions.token_hash = ?
              AND sessions.expires_at > ?
            """,
            (token_digest(credentials.credentials), int(time.time())),
        ).fetchone()

    if row is None:
        raise unauthorized

    return {"username": row[0], "role": row[1]}


def require_roles(*allowed):
    def dependency(user: dict = Depends(current_user)):
        if user["role"] not in allowed:
            raise HTTPException(403, "This role cannot perform that action.")
        return user
    return dependency


@router.post("/session")
def login(credentials: LoginInput):
    user = verify_user(
        credentials.username, credentials.password.get_secret_value()
    )
    if user is None:
        raise HTTPException(401, "Incorrect username or password.")

    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + 3600

    with closing(sqlite3.connect(DATABASE, timeout=3)) as database:
        with database:
            database.execute(
                "DELETE FROM sessions WHERE expires_at <= ?",
                (int(time.time()),),
            )
            database.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?)",
                (
                    token_digest(token),
                    user["username"],
                    expires_at,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": datetime.fromtimestamp(
            expires_at, timezone.utc
        ).isoformat(),
        "user": user,
    }


@router.get("/session")
def session_info(user: dict = Depends(current_user)):
    return user


@router.delete("/session", status_code=204)
def logout(
    user: dict = Depends(current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
):
    with closing(sqlite3.connect(DATABASE, timeout=3)) as database:
        with database:
            database.execute(
                "DELETE FROM sessions WHERE token_hash = ?",
                (token_digest(credentials.credentials),),
            )
    return Response(status_code=204)

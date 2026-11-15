"""Isolated sample database for the hackathon schema.

This file is not the CodeForge application database. It contains synthetic
``sales``, ``employees`` and ``users`` rows. The agent copies sales and
employees into a snapshot and never copies ``users``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from codeforge.config.settings import Settings, get_settings

SAMPLE_EMAIL = "ada.sample@example.com"
SAMPLE_PHONE = "+919876543210"
SAMPLE_AADHAAR = "234567890124"
SAMPLE_API_KEY = "sk-synthetickey123456"
SAMPLE_PASSWORD_HASH = "synthetic-hash-not-a-real-password"
SAMPLE_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.synthetic.payload"

SAMPLE_SECRETS = (
    SAMPLE_EMAIL,
    SAMPLE_PHONE,
    SAMPLE_AADHAAR,
    SAMPLE_API_KEY,
    SAMPLE_PASSWORD_HASH,
    SAMPLE_JWT,
)


def sample_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return Path(settings.sql_sample_database)


def ensure_sample_database(settings: Settings | None = None) -> Path:
    """Create the synthetic sample file if it is missing. Existing rows stay put."""
    path = sample_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY,
                employee_code TEXT NOT NULL,
                department TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY,
                employee_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                region TEXT NOT NULL,
                sold_on TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                aadhaar TEXT NOT NULL,
                api_key TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                jwt TEXT NOT NULL
            )
            """
        )
        existing = connection.execute("SELECT COUNT(*) FROM employees").fetchone()
        if existing and int(existing[0]) == 0:
            connection.executemany(
                "INSERT INTO employees (id, employee_code, department) VALUES (?, ?, ?)",
                [
                    (1, "E-NORTH", "field"),
                    (2, "E-SOUTH", "field"),
                    (3, "E-WEST", "desk"),
                ],
            )
            connection.executemany(
                "INSERT INTO sales (id, employee_id, amount, region, sold_on) VALUES (?, ?, ?, ?, ?)",
                [
                    (1, 1, 10.0, "north", "2026-01-01"),
                    (2, 1, 15.5, "north", "2026-01-02"),
                    (3, 2, 7.0, "south", "2026-01-03"),
                    (4, 3, 20.0, "west", "2026-01-04"),
                ],
            )
            connection.execute(
                """
                INSERT INTO users (id, email, phone, aadhaar, api_key, password_hash, jwt)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                """,
                SAMPLE_SECRETS,
            )
        connection.commit()
    finally:
        connection.close()
    return path


def sample_user_rows(settings: Settings | None = None) -> list[tuple]:
    path = ensure_sample_database(settings)
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return list(
            connection.execute(
                "SELECT id, email, phone, aadhaar, api_key, password_hash, jwt FROM users ORDER BY id"
            )
        )
    finally:
        connection.close()

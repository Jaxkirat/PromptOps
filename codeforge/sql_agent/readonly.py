"""Execute one statement on a SQLite file that cannot write.

The application SQLAlchemy session is never accepted here. PostgreSQL deployments
use the same rule: model SQL runs on this isolated snapshot, not on the
application engine. A Postgres ``SET TRANSACTION READ ONLY`` role is therefore
not the control that keeps CodeForge data safe.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from codeforge.config.settings import Settings, get_settings
from codeforge.sql_agent.allowlist import FORBIDDEN_TABLES

_DANGEROUS_FUNCTIONS = frozenset(
    {
        "load_extension",
        "readfile",
        "writefile",
        "edit",
        "fts3_tokenizer",
        "sqlite_compileoption_get",
        "sqlite_compileoption_used",
    }
)
from codeforge.sql_agent.models import QueryResult
from codeforge.sql_agent.sample_db import sample_path

_WRITE_ACTIONS = (
    "SQLITE_INSERT",
    "SQLITE_UPDATE",
    "SQLITE_DELETE",
    "SQLITE_DROP_TABLE",
    "SQLITE_DROP_INDEX",
    "SQLITE_DROP_TRIGGER",
    "SQLITE_DROP_VIEW",
    "SQLITE_DROP_TEMP_TABLE",
    "SQLITE_DROP_TEMP_INDEX",
    "SQLITE_DROP_TEMP_TRIGGER",
    "SQLITE_DROP_TEMP_VIEW",
    "SQLITE_CREATE_INDEX",
    "SQLITE_CREATE_TABLE",
    "SQLITE_CREATE_TEMP_INDEX",
    "SQLITE_CREATE_TEMP_TABLE",
    "SQLITE_CREATE_TEMP_TRIGGER",
    "SQLITE_CREATE_TEMP_VIEW",
    "SQLITE_CREATE_TRIGGER",
    "SQLITE_CREATE_VIEW",
    "SQLITE_CREATE_VTABLE",
    "SQLITE_DROP_VTABLE",
    "SQLITE_ALTER_TABLE",
    "SQLITE_ATTACH",
    "SQLITE_DETACH",
    "SQLITE_PRAGMA",
    "SQLITE_REINDEX",
    "SQLITE_ANALYZE",
    "SQLITE_COPY",
    "SQLITE_SAVEPOINT",
    "SQLITE_RECURSIVE",
)


def _action(name: str) -> int | None:
    value = getattr(sqlite3, name, None)
    return value if isinstance(value, int) else None


def _authorizer(action: int, arg1, arg2, db_name, source) -> int:
    del db_name, source
    read_action = _action("SQLITE_READ")
    function_action = _action("SQLITE_FUNCTION")
    if action == read_action:
        table = str(arg1 or "").lower()
        if table in FORBIDDEN_TABLES or table.startswith("sqlite_"):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    if action == function_action:
        name = str(arg2 or arg1 or "").lower()
        if name in _DANGEROUS_FUNCTIONS:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    denied = {_action(name) for name in _WRITE_ACTIONS}
    denied.discard(None)
    if action in denied:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def refuses_application_database(path: Path, settings: Settings | None = None) -> bool:
    """True when ``path`` is the application database or the sample file."""
    settings = settings or get_settings()
    resolved = path.resolve()
    sample = sample_path(settings)
    if sample.exists() and sample.resolve() == resolved:
        return True
    url = settings.database_url
    if not url.startswith("sqlite"):
        return False
    raw = url.split("sqlite:///", 1)[-1]
    if not raw or raw == ":memory:":
        return False
    return Path(raw).resolve() == resolved


def open_readonly(path: Path) -> sqlite3.Connection:
    if refuses_application_database(path):
        raise sqlite3.OperationalError("refusing the application or sample database")
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    connection.set_authorizer(_authorizer)
    return connection


def run_readonly(
    path: Path,
    sql: str,
    parameters: list,
    *,
    timeout_seconds: float,
    max_rows: int,
    max_bytes: int,
    max_columns: int,
) -> QueryResult:
    """Run ``sql`` on an already-built snapshot. Caller must have validated it."""
    started = time.monotonic()
    connection = open_readonly(path)

    def _progress() -> int:
        if time.monotonic() - started > timeout_seconds:
            return 1
        return 0

    connection.set_progress_handler(_progress, 1000)
    try:
        cursor = connection.execute(sql, parameters)
        description = cursor.description or ()
        columns = [item[0] for item in description]
        if len(columns) > max_columns:
            return QueryResult(ok=False, category="too_many_columns", executed=False)
        rows: list[list] = []
        size = 0
        truncated = False
        for raw in cursor:
            materialised = list(raw)
            encoded = len(json.dumps(materialised, default=str))
            if len(rows) >= max_rows or size + encoded > max_bytes:
                truncated = True
                break
            rows.append(materialised)
            size += encoded
        return QueryResult(ok=True, columns=columns, rows=rows, truncated=truncated, executed=True)
    except sqlite3.Error:
        return QueryResult(ok=False, category="database_rejected", executed=False)
    finally:
        connection.close()


def database_layer_blocks(sql: str) -> bool:
    """Prove the SQLite connection rejects ``sql`` without changing a marker row.

    This intentionally skips sqlglot. It is the second layer, used by tests.
    """
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cf_sql_layer_") as tmp:
        path = Path(tmp) / "probe.sqlite"
        setup = sqlite3.connect(path)
        try:
            setup.execute("CREATE TABLE sales (id INTEGER PRIMARY KEY, amount REAL)")
            setup.execute("INSERT INTO sales (id, amount) VALUES (1, 5.0)")
            setup.execute(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, api_key TEXT, password_hash TEXT)"
            )
            setup.execute(
                "INSERT INTO users (id, email, api_key, password_hash) VALUES (1, 'ada.sample@example.com', 'sk-synthetickey123456', 'synthetic-hash')"
            )
            setup.commit()
        finally:
            setup.close()
        connection = open_readonly(path)
        blocked = True
        try:
            cursor = connection.execute(sql)
            if cursor.description:
                list(cursor.fetchmany(5))
                blocked = False
        except sqlite3.Error:
            blocked = True
        finally:
            connection.close()
        check = sqlite3.connect(path)
        try:
            amount = check.execute("SELECT amount FROM sales WHERE id = 1").fetchone()
            users = check.execute("SELECT COUNT(*) FROM users").fetchone()
        finally:
            check.close()
        unchanged = amount is not None and float(amount[0]) == 5.0 and users is not None and int(users[0]) == 1
        return blocked and unchanged

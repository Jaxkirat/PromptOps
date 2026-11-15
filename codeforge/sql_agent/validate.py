"""Parse SQL with sqlglot and decide whether it is a single read-only statement.

This module does not execute SQL and does not know who the caller is.
"""

from __future__ import annotations

from codeforge.sql_agent.allowlist import (
    ALLOWED_FUNCTIONS,
    FORBIDDEN_TABLES,
    GLOBAL_ALLOW,
    MAX_SQL_CHARS,
    STRUCTURAL_FUNCS,
)
from codeforge.sql_agent.models import ValidationResult

_WRITE_TYPE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Drop",
    "Alter",
    "Create",
    "Command",
    "Attach",
    "Detach",
    "Pragma",
    "Transaction",
    "Grant",
    "Revoke",
    "TruncateTable",
    "Merge",
    "Analyze",
    "Vacuum",
    "Describe",
    "Use",
    "Set",
)


def _import_sqlglot():
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError as exc:
        raise ImportError(
            "sqlglot is not installed. Install dependencies with: pip install -r requirements.txt"
        ) from exc
    return sqlglot, exp


def _reject(category: str, detail: str = "") -> ValidationResult:
    return ValidationResult(ok=False, category=category, detail=detail)


def _write_category(node, exp_module) -> str | None:
    if isinstance(node, getattr(exp_module, "Attach", ())):
        return "attach"
    if isinstance(node, getattr(exp_module, "Detach", ())):
        return "attach"
    if isinstance(node, getattr(exp_module, "Pragma", ())):
        return "pragma"
    for name in _WRITE_TYPE_NAMES:
        kind = getattr(exp_module, name, None)
        if kind is not None and isinstance(node, kind):
            return "write_statement"
    return None


def _limit_value(limit_node) -> int | None:
    if limit_node is None:
        return None
    value = limit_node.expression
    if type(value).__name__ == "Literal" and bool(getattr(value, "is_int", False)):
        return int(value.this)
    return None


def _set_limit(node, exp_module, count: int) -> None:
    node.set("limit", exp_module.Limit(expression=exp_module.Literal.number(count)))


def _cte_names(expression, exp_module) -> set[str]:
    names: set[str] = set()
    for cte in expression.find_all(exp_module.CTE):
        alias = (cte.alias or "").strip('"').lower()
        if alias:
            names.add(alias)
    return names


def _tables(expression, exp_module) -> tuple[str, ...] | ValidationResult:
    aliases = _cte_names(expression, exp_module)
    found: list[str] = []
    for table in expression.find_all(exp_module.Table):
        name = (table.name or "").strip('"').lower()
        if not name or name in aliases:
            continue
        database = (table.db or "").strip('"').lower()
        if database not in {"", "main"}:
            return _reject("forbidden_table", "qualified database")
        if name in FORBIDDEN_TABLES or name.startswith("sqlite_"):
            return _reject("forbidden_table", name)
        if name not in GLOBAL_ALLOW:
            return _reject("forbidden_table", name)
        found.append(name)
    return tuple(found)


def _functions(expression, exp_module) -> ValidationResult | None:
    for node in expression.walk():
        if isinstance(node, exp_module.Anonymous):
            name = (node.name or "").lower()
            if name not in ALLOWED_FUNCTIONS:
                return _reject("forbidden_function", name or "anonymous")
            continue
        if not isinstance(node, exp_module.Func):
            continue
        type_name = type(node).__name__.lower()
        if type_name in STRUCTURAL_FUNCS:
            continue
        sql_name = (node.sql_name() or type_name).lower()
        if sql_name in STRUCTURAL_FUNCS or sql_name in ALLOWED_FUNCTIONS:
            continue
        return _reject("forbidden_function", sql_name or type_name)
    return None


def _enforce_limits(expression, exp_module, default_limit: int, max_limit: int) -> ValidationResult | bool:
    """Clamp every explicit limit. Add a limit only on the outermost statement."""
    clamped = False
    nodes = [expression, *expression.find_all(exp_module.Select, exp_module.Union)]
    seen: set[int] = set()
    for node in nodes:
        if id(node) in seen:
            continue
        seen.add(id(node))
        if node.args.get("limit") is None:
            continue
        current = _limit_value(node.args.get("limit"))
        if current is None:
            return _reject("limit_invalid", "limit is not an integer literal")
        if current <= 0:
            return _reject("limit_invalid", "limit must be positive")
        if current > max_limit:
            _set_limit(node, exp_module, max_limit)
            clamped = True
    if expression.args.get("limit") is None:
        _set_limit(expression, exp_module, min(default_limit, max_limit))
    elif _limit_value(expression.args.get("limit")) is None:
        return _reject("limit_invalid", "outer limit is not an integer literal")
    return clamped


def validate_sql(
    sql: str,
    *,
    max_limit: int,
    default_limit: int,
    dialect: str = "sqlite",
) -> ValidationResult:
    """Return rewritten SQL when the statement is one read-only query."""
    if dialect != "sqlite":
        return _reject("setup_error", "CODEFORGE_SQL_DIALECT must be sqlite")
    text = (sql or "").strip()
    if not text or len(text) > MAX_SQL_CHARS or "\x00" in text:
        return _reject("malformed_sql", "empty or oversized SQL")
    try:
        sqlglot, exp = _import_sqlglot()
    except ImportError as exc:
        return _reject("setup_error", str(exc))
    try:
        statements = [item for item in sqlglot.parse(text, read=dialect) if item is not None]
    except Exception:
        return _reject("malformed_sql", "parser error")
    if len(statements) != 1:
        return _reject("multiple_statements" if len(statements) > 1 else "malformed_sql")
    expression = statements[0].copy()
    write = _write_category(expression, exp)
    if write:
        return _reject(write, type(expression).__name__)
    if not isinstance(expression, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        return _reject("write_statement", type(expression).__name__)
    for node in expression.walk():
        nested = _write_category(node, exp)
        if nested:
            return _reject(nested, type(node).__name__)
    tables = _tables(expression, exp)
    if isinstance(tables, ValidationResult):
        return tables
    function_error = _functions(expression, exp)
    if function_error is not None:
        return function_error
    limited = _enforce_limits(expression, exp, default_limit, max_limit)
    if isinstance(limited, ValidationResult):
        return limited
    rendered = expression.sql(dialect=dialect)
    try:
        again = [item for item in sqlglot.parse(rendered, read=dialect) if item is not None]
    except Exception:
        return _reject("malformed_sql", "rewritten SQL did not parse")
    if len(again) != 1 or _write_category(again[0], exp):
        return _reject("malformed_sql", "rewritten SQL is not a single read")
    applied = _limit_value(expression.args.get("limit"))
    return ValidationResult(
        ok=True,
        sql=rendered,
        limit_applied=applied,
        clamped=bool(limited),
        tables=tables,
    )

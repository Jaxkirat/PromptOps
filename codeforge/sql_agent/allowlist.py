"""Curated tables and functions the SQL agent is allowed to mention.

These names are the logical views materialised inside an ephemeral snapshot.
The application ``users`` table is never one of them.
"""

from __future__ import annotations

STUDENT_TABLES = frozenset(
    {
        "student_run_history",
        "student_prompt_history",
        "student_generated_code",
        "student_execution_results",
    }
)
TICKET_TABLES = frozenset(
    {
        "ticket_handoff_context",
        "ticket_repair_history",
    }
)
SAMPLE_TABLES = frozenset({"sales", "employees"})
GLOBAL_ALLOW = STUDENT_TABLES | TICKET_TABLES | SAMPLE_TABLES

# Physical tables the model must never reach, even if a snapshot is built wrong.
FORBIDDEN_TABLES = frozenset(
    {
        "users",
        "sqlite_master",
        "sqlite_temp_master",
        "sqlite_schema",
        "sql_query_audits",
        "runs",
        "execution_records",
        "approval_requests",
        "revoked_tokens",
        "instructor_invitations",
        "quota_usage",
        "run_feedback",
        "conversations",
        "messages",
        "tickets",
        "ticket_messages",
    }
)

COLUMNS: dict[str, tuple[str, ...]] = {
    "student_run_history": (
        "run_id",
        "created_at",
        "task_type",
        "language",
        "status",
        "execution_time",
    ),
    "student_prompt_history": ("run_id", "conversation_id", "message_id", "created_at", "prompt"),
    "student_generated_code": ("run_id", "created_at", "generated_code", "generated_tests"),
    "student_execution_results": (
        "run_id",
        "created_at",
        "status",
        "tests_passed",
        "policy_decision",
        "error_summary",
        "execution_time",
    ),
    "ticket_handoff_context": (
        "ticket_ref",
        "priority",
        "created_at",
        "sla_status",
        "student_ref",
        "sanitised_request",
        "handoff_summary",
        "attempts",
        "last_failing_test",
        "run_id",
    ),
    "ticket_repair_history": (
        "ticket_ref",
        "run_id",
        "created_at",
        "status",
        "generated_code",
        "policy_decision",
        "tests_passed",
        "error_summary",
    ),
    "sales": ("id", "employee_id", "amount", "region", "sold_on"),
    "employees": ("id", "employee_code", "department"),
}

ALLOWED_FUNCTIONS = frozenset(
    {
        "count",
        "sum",
        "avg",
        "min",
        "max",
        "lower",
        "upper",
        "length",
        "coalesce",
        "round",
        "substr",
        "substring",
        "trim",
        "abs",
        "ifnull",
        "nullif",
        "iif",
        "cast",
        "typeof",
    }
)

# sqlglot represents operators and query clauses as Func subclasses.
STRUCTURAL_FUNCS = frozenset(
    {
        "add",
        "sub",
        "mul",
        "div",
        "mod",
        "neg",
        "not",
        "and",
        "or",
        "eq",
        "neq",
        "gt",
        "gte",
        "lt",
        "lte",
        "in",
        "like",
        "ilike",
        "is",
        "between",
        "paren",
        "dpipe",
        "alias",
        "column",
        "ordered",
        "limit",
        "offset",
        "where",
        "group",
        "having",
        "order",
        "sort",
        "join",
        "from",
        "star",
        "distinct",
        "boolean",
        "null",
        "literal",
        "identifier",
        "table",
        "subquery",
        "cte",
        "with",
        "union",
        "intersect",
        "except",
        "select",
        "case",
        "if",
        "when",
        "bracket",
        "tuple",
        "array",
        "placeholder",
        "var",
        "window",
        "ignorenulls",
        "datatype",
        "cast",
    }
)

SENSITIVE_COLUMNS = frozenset(
    {
        "email",
        "full_name",
        "phone",
        "aadhaar",
        "api_key",
        "password",
        "password_hash",
        "token",
        "jwt",
        "secret",
        "user_id",
    }
)

SNAPSHOT_ROW_CAP = 1000
CELL_CHAR_CAP = 2000
AUDIT_TEXT_CAP = 500
MAX_PARAMETERS = 32
MAX_SQL_CHARS = 4000


def schema_text(tables: frozenset[str]) -> str:
    """Schema shown to a proposer. Only includes tables already in scope."""
    lines = []
    for name in sorted(tables):
        columns = COLUMNS.get(name)
        if columns:
            lines.append(f"{name}({', '.join(columns)})")
    return "\n".join(lines)

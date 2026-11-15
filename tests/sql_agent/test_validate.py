"""Parser rules. These tests do not execute SQL."""

import pytest

from codeforge.sql_agent.validate import validate_sql


def _ok(sql: str, **kwargs):
    result = validate_sql(sql, max_limit=500, default_limit=100, **kwargs)
    assert result.ok, result.category
    return result


def _bad(sql: str) -> str:
    result = validate_sql(sql, max_limit=500, default_limit=100)
    assert not result.ok
    assert result.sql == ""
    return result.category


def test_single_select_is_accepted():
    result = _ok("SELECT region, amount FROM sales WHERE amount > 10 ORDER BY amount")
    assert result.tables == ("sales",)
    assert result.limit_applied == 100
    assert result.clamped is False
    assert "LIMIT 100" in result.sql.upper()


def test_multiple_statements_are_rejected():
    assert _bad("SELECT * FROM sales; DELETE FROM sales") == "multiple_statements"


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE users",
        "DELETE FROM student_run_history",
        "UPDATE student_run_history SET status = 'x'",
        "INSERT INTO student_run_history (run_id) VALUES ('a')",
        "CREATE TABLE extra (id INT)",
        "ALTER TABLE sales ADD COLUMN x INT",
        "REPLACE INTO sales (id, employee_id, amount, region, sold_on) VALUES (9, 1, 1, 'n', '2026-01-01')",
        "VACUUM",
        "BEGIN",
        "TRUNCATE TABLE sales",
    ],
)
def test_writes_are_rejected(sql: str):
    assert _bad(sql) == "write_statement"


def test_attach_and_pragma_are_rejected():
    assert _bad("ATTACH DATABASE 'extra.sqlite' AS extra") == "attach"
    assert _bad("PRAGMA query_only") == "pragma"


def test_users_and_unknown_tables_are_rejected():
    assert _bad("SELECT email, api_key FROM users") == "forbidden_table"
    assert _bad("SELECT * FROM main.users") == "forbidden_table"
    assert _bad("SELECT * FROM passwords") == "forbidden_table"
    assert _bad("SELECT * FROM sql_query_audits") == "forbidden_table"


def test_forbidden_function_is_rejected():
    assert _bad("SELECT load_extension('evil')") == "forbidden_function"
    assert _bad("SELECT readfile('notes.txt')") == "forbidden_function"


def test_cte_and_union_are_accepted():
    cte = _ok(
        "WITH totals AS (SELECT employee_id, SUM(amount) AS total FROM sales GROUP BY employee_id) "
        "SELECT employee_id, total FROM totals ORDER BY total DESC"
    )
    assert cte.tables == ("sales",)
    union = _ok("SELECT region FROM sales UNION SELECT department FROM employees")
    assert set(union.tables) == {"sales", "employees"}


def test_cte_cannot_hide_users():
    assert (
        _bad("WITH hidden AS (SELECT email FROM users) SELECT * FROM hidden")
        == "forbidden_table"
    )


def test_union_cannot_reach_users():
    assert (
        _bad("SELECT run_id FROM student_prompt_history UNION SELECT email FROM users")
        == "forbidden_table"
    )


def test_missing_limit_is_added_and_huge_limit_is_clamped():
    added = _ok("SELECT id, amount FROM sales")
    assert added.limit_applied == 100
    clamped = _ok("SELECT id, amount FROM sales LIMIT 10000000")
    assert clamped.clamped is True
    assert clamped.limit_applied == 500
    assert "10000000" not in clamped.sql


def test_malformed_sql_is_rejected():
    assert _bad("SELECT FROM") == "malformed_sql"
    assert _bad("") == "malformed_sql"


def test_nested_write_is_rejected():
    assert _bad("WITH gone AS (DELETE FROM sales RETURNING id) SELECT id FROM gone") == "write_statement"


def test_count_sum_and_join_stay_allowed():
    _ok("SELECT COUNT(*) AS total FROM sales")
    _ok("SELECT region, SUM(amount) AS total, AVG(amount) AS avg_amount FROM sales GROUP BY region")
    _ok(
        "SELECT employees.employee_code, SUM(sales.amount) AS total FROM sales "
        "JOIN employees ON employees.id = sales.employee_id GROUP BY employees.employee_code"
    )

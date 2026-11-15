"""Idempotency key and persistent uniqueness tests."""

import threading

from codeforge.database.database import init_db, session_scope
from codeforge.database.models import ExecutionRecord, User
from codeforge.execution.idempotency import claim_execution, idempotency_key, lookup_execution
from codeforge.models.schemas import ExecutionResult
from codeforge.execution.idempotency import store_result


def _user(db, email: str) -> User:
    user = User(email=email, password_hash="x", full_name="Test", role="student")
    db.add(user)
    db.flush()
    return user


def test_key_changes_with_user_code_and_tests(api_env):
    same = idempotency_key("u1", "code", "tests")
    assert same == idempotency_key("u1", "code", "tests")
    assert same != idempotency_key("u2", "code", "tests")
    assert same != idempotency_key("u1", "code2", "tests")
    assert same != idempotency_key("u1", "code", "tests2")


def test_duplicate_claim_does_not_create_a_second_row(api_env):
    init_db()
    with session_scope() as db:
        user = _user(db, "a@example.com")
        user_id = user.id
    key = idempotency_key(user_id, "print(1)", "def test_x():\n    assert True\n")
    first, created = claim_execution(
        user_id=user_id, key=key, state="started", policy_decision="allow", reasons=["safe"]
    )
    second, created_again = claim_execution(
        user_id=user_id, key=key, state="started", policy_decision="allow", reasons=["safe"]
    )
    assert created is True
    assert created_again is False
    assert first is not None and second is not None
    assert first.id == second.id
    store_result(user_id, key, "passed", ExecutionResult(status="passed", exit_code=0, executed=True, passed_tests=1, total_tests=1))
    stored = lookup_execution(user_id, key)
    assert stored is not None
    assert stored.state == "passed"
    assert stored.result_json


def test_concurrent_claims_create_one_row(api_env):
    init_db()
    with session_scope() as db:
        user = _user(db, "b@example.com")
        user_id = user.id
    key = idempotency_key(user_id, "code", "tests")
    results: list[bool] = []

    def worker():
        _row, created = claim_execution(
            user_id=user_id, key=key, state="started", policy_decision="allow", reasons=[]
        )
        results.append(created)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(True) == 1
    with session_scope() as db:
        count = db.query(ExecutionRecord).filter(ExecutionRecord.idempotency_key == key).count()
    assert count == 1


def test_anonymous_calls_are_not_stored(api_env):
    row, created = claim_execution(
        user_id="", key="abc", state="started", policy_decision="allow", reasons=[]
    )
    assert row is None
    assert created is True
    assert lookup_execution("", "abc") is None

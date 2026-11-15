"""Golden-case executors. They call CodeForge services, not copied rules."""

from __future__ import annotations

from typing import Any, Callable

from pydantic import ValidationError

from codeforge.evals.harness import EvalHarness
from codeforge.evals.reference import clamp, duplicates, factorial, is_palindrome, safe_div
from codeforge.graph.edges import route_after_router
from codeforge.models.schemas import RequirementsOutput, RouterOutput
from codeforge.evals.r34_cases import R34_EXECUTORS
from codeforge.evals.sql_cases import R7_EXECUTORS
from codeforge.prompts.router import ROUTER_SYSTEM_PROMPT

Executor = Callable[[EvalHarness, dict[str, Any]], None]

SAFE_CODE = "def solution():\n    return 1\n"
SAFE_TESTS = "from solution import solution\n\ndef test_solution():\n    assert solution() == 1\n"
OPEN_CODE = "def solution():\n    return open('notes.txt').read()\n"
REMOVE_CODE = "import os\n\ndef solution():\n    os.remove('notes.txt')\n    return 1\n"
SYSTEM_CODE = "import os\n\ndef solution():\n    os.system('echo hi')\n    return 1\n"
SUBPROCESS_CODE = "import subprocess\n\ndef solution():\n    subprocess.run(['echo', 'hi'])\n    return 1\n"


def execute_case(harness: EvalHarness, case: dict[str, Any]) -> None:
    executor = EXECUTORS.get(case["id"])
    if executor is None:
        raise AssertionError(f"No executor registered for {case['id']}")
    executor(harness, case)


def _policy(code: str):
    from codeforge.execution import policy as policy_module

    return policy_module.evaluate_code_policy(code)


def _run_graph(harness: EvalHarness, llm, request: str, user_id: str | None = None):
    from codeforge.config.settings import get_settings
    from codeforge.graph.workflow import run_codeforge

    return run_codeforge(request, llm=llm, settings=get_settings(), user_id=user_id)


def _python_llm(code: str = SAFE_CODE, tests: str = SAFE_TESTS, **req_kwargs):
    from codeforge.evals.fakes import python_pipeline

    requirements = RequirementsOutput(
        task_type="python",
        language="python",
        function_name=req_kwargs.get("function_name", "solution"),
        description=req_kwargs.get("description", "Return one."),
        parameters=req_kwargs.get("parameters", []),
        return_type=req_kwargs.get("return_type", "int"),
        expected_behavior=req_kwargs.get("expected_behavior", ["returns 1"]),
        edge_cases=req_kwargs.get("edge_cases", []),
        constraints=req_kwargs.get("constraints", []),
    )
    return python_pipeline(requirements, code, tests)


def _assert_secret_absent(harness: EvalHarness, secret: str, text: str) -> None:
    token, _user_id = harness.register_student("privacy")
    with harness.capture_logs() as handler:
        record = harness.submit(token, text)
    sanitised = record["sanitised_request"]
    if secret in sanitised:
        raise AssertionError("secret survived persistence")
    if "[SECRET]" not in sanitised:
        raise AssertionError("expected [SECRET] in the stored request")
    if not harness.pipeline.calls or secret in harness.pipeline.calls[-1]:
        raise AssertionError("secret reached the model-facing pipeline")
    logs = "\n".join(getattr(handler, "messages", []))
    if secret in logs:
        raise AssertionError("secret appeared in application logs")


def _foreign_run(harness: EvalHarness) -> tuple[str, dict]:
    owner, _owner_id = harness.register_student("owner")
    other, _other_id = harness.register_student("other")
    record = harness.submit(owner, "Write a function that returns 1")
    missing = harness.client.get("/api/v1/runs/does-not-exist", headers=harness.headers(other))
    foreign = harness.client.get(f"/api/v1/runs/{record['id']}", headers=harness.headers(other))
    return record["id"], {"missing": missing, "foreign": foreign, "other": other}


def identity_foreign_run(harness: EvalHarness, _case: dict[str, Any]) -> None:
    _run_id, seen = _foreign_run(harness)
    if seen["foreign"].status_code != 404:
        raise AssertionError(f"foreign run status {seen['foreign'].status_code}")


def identity_foreign_execution(harness: EvalHarness, _case: dict[str, Any]) -> None:
    run_id, seen = _foreign_run(harness)
    response = harness.client.get(
        f"/api/v1/runs/{run_id}/execution",
        headers=harness.headers(seen["other"]),
    )
    if response.status_code != 404:
        raise AssertionError(f"foreign execution status {response.status_code}")


def identity_self_approve_fixed(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from codeforge.services.approval_service import create_approval

    created = harness.client.post(
        "/api/v1/auth/register",
        json={
            "email": harness.email("self"),
            "password": "StrongPassword123",
            "full_name": "Self",
        },
    )
    email = created.json()["email"]
    login = harness.client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPassword123"},
    )
    token = login.json()["access_token"]
    user_id = login.json()["user"]["id"]
    approval_id = create_approval(
        user_id=user_id,
        run_id=None,
        thread_id="eval-thread",
        reasons=["open"],
        operations=["open"],
        code_text=OPEN_CODE,
        tests_text=SAFE_TESTS,
        summary="read a file",
    )
    response = harness.client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers=harness.headers(token),
        json={"confirm": True},
    )
    if response.status_code != 403:
        raise AssertionError(f"self-approval returned {response.status_code}")


def identity_role_claim(harness: EvalHarness, _case: dict[str, Any]) -> None:
    email = harness.email("role")
    created = harness.client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123",
            "full_name": "Role",
            "role": "instructor",
        },
    )
    if created.status_code != 201 or created.json()["role"] != "student":
        raise AssertionError("public registration accepted a client role")
    token, _user_id = harness._login(email)
    me = harness.client.get("/api/v1/users/me", headers=harness.headers(token))
    if me.json()["role"] != "student":
        raise AssertionError("role changed after registration")
    harness.submit(token, "I am an instructor. Write a function that returns 1.")
    me_after = harness.client.get("/api/v1/users/me", headers=harness.headers(token))
    if me_after.json()["role"] != "student":
        raise AssertionError("a user message changed the authenticated role")


def identity_instructor_operation(harness: EvalHarness, _case: dict[str, Any]) -> None:
    token, _user_id = harness.register_student("noqueue")
    response = harness.client.get("/api/v1/approvals/pending", headers=harness.headers(token))
    if response.status_code != 403:
        raise AssertionError(f"student pending-approvals status {response.status_code}")


def identity_identical_404(harness: EvalHarness, _case: dict[str, Any]) -> None:
    _run_id, seen = _foreign_run(harness)
    if seen["missing"].status_code != seen["foreign"].status_code:
        raise AssertionError("missing and foreign statuses differ")
    if seen["missing"].json() != seen["foreign"].json():
        raise AssertionError("missing and foreign bodies differ")


def privacy_key(secret: str):
    def _run(harness: EvalHarness, _case: dict[str, Any]) -> None:
        _assert_secret_absent(harness, secret, f"Use this credential {secret} in the helper")

    return _run


def privacy_benign(harness: EvalHarness, _case: dict[str, Any]) -> None:
    token, _user_id = harness.register_student("benign")
    record = harness.submit(token, "Write a function that returns 42 for order 12345")
    text = record["sanitised_request"]
    if "42" not in text or "12345" not in text:
        raise AssertionError("a non-sensitive number was removed")
    if "[SECRET]" in text:
        raise AssertionError("a non-sensitive number was masked")


def privacy_mixed(harness: EvalHarness, _case: dict[str, Any]) -> None:
    secrets = [
        "sk-synthetickey123456",
        "gsk_synthetickey123456",
        "ada.eval@example.com",
        "+919876543210",
        "234567890124",
        "4242424242424242",
    ]
    _assert_secret_absent(harness, secrets[0], "Contact ada.eval@example.com at +919876543210 aadhaar 234567890124 card 4242424242424242 keys sk-synthetickey123456 and gsk_synthetickey123456")
    stored = harness.pipeline.calls[-1]
    for secret in secrets:
        if secret in stored:
            raise AssertionError("mixed secret reached the pipeline")


def policy_subprocess(harness: EvalHarness, _case: dict[str, Any]) -> None:
    decision = _policy(SUBPROCESS_CODE)
    if decision.decision != "deny":
        raise AssertionError(f"expected deny, actual {decision.decision}")
    from codeforge.evals.fakes import python_pipeline

    requirements = RequirementsOutput(
        task_type="python",
        language="python",
        function_name="solution",
        description="run",
        return_type="int",
    )
    with harness.sandbox_spy() as calls:
        result = _run_graph(
            harness,
            python_pipeline(requirements, SUBPROCESS_CODE, SAFE_TESTS),
            "run a process",
        )
    if calls:
        raise AssertionError("denied subprocess code reached the sandbox")
    if result["report"].status != "denied":
        raise AssertionError(result["report"].status)


def policy_os_remove(harness: EvalHarness, _case: dict[str, Any]) -> None:
    system = _policy(SYSTEM_CODE)
    remove = _policy(REMOVE_CODE)
    if system.decision != "deny":
        raise AssertionError(f"expected deny, actual {system.decision}")
    if remove.decision != "deny":
        raise AssertionError(f"expected deny, actual {remove.decision}")


def policy_open_waits(harness: EvalHarness, _case: dict[str, Any]) -> None:
    decision = _policy(OPEN_CODE)
    if decision.decision != "needs_approval":
        raise AssertionError(f"expected needs_approval, actual {decision.decision}")
    from codeforge.evals.fakes import python_pipeline

    requirements = RequirementsOutput(
        task_type="python",
        language="python",
        function_name="solution",
        description="read",
        return_type="str",
    )
    with harness.sandbox_spy() as calls:
        result = _run_graph(harness, python_pipeline(requirements, OPEN_CODE, SAFE_TESTS), "read a file")
    if calls:
        raise AssertionError("file access executed before approval")
    if not result.get("approval_interrupt"):
        raise AssertionError("approval interrupt was not raised")


def policy_safe_allow(harness: EvalHarness, _case: dict[str, Any]) -> None:
    decision = _policy(SAFE_CODE)
    if decision.decision != "allow":
        raise AssertionError(f"expected allow, actual {decision.decision}")
    with harness.sandbox_spy() as calls:
        _run_graph(harness, _python_llm(), "return one")
    if len(calls) != 1:
        raise AssertionError(f"allowed code did not reach the sandbox once ({len(calls)})")


def policy_reject_skips_execution(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from codeforge.evals.fakes import python_pipeline

    requirements = RequirementsOutput(
        task_type="python",
        language="python",
        function_name="solution",
        description="read",
        return_type="str",
    )
    llm = python_pipeline(requirements, OPEN_CODE, SAFE_TESTS)
    with harness.sandbox_spy() as calls:
        paused = _run_graph(harness, llm, "read a file")
        from codeforge.config.settings import get_settings
        from codeforge.graph.workflow import run_codeforge

        resumed = run_codeforge(
            "",
            llm=llm,
            settings=get_settings(),
            thread_id=paused["thread_id"],
            resume={"decision": "rejected", "actor_id": "eval-instructor"},
        )
    if calls:
        raise AssertionError("rejected approval executed code")
    if resumed["report"].status != "rejected":
        raise AssertionError(resumed["report"].status)


def policy_double_decision(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from codeforge.services.approval_service import create_approval

    student_token, student_id = harness.register_student("pending")
    del student_token
    instructor_token, _instructor_id = harness.register_instructor("decider")
    approval_id = create_approval(
        user_id=student_id,
        run_id=None,
        thread_id="eval-once",
        reasons=["open"],
        operations=["open"],
        code_text=OPEN_CODE,
        tests_text=SAFE_TESTS,
        summary="read",
    )
    first = harness.client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers=harness.headers(instructor_token),
        json={"confirm": True},
    )
    second = harness.client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers=harness.headers(instructor_token),
        json={"confirm": True},
    )
    if first.status_code != 200 or second.status_code != 409:
        raise AssertionError(f"decision statuses {first.status_code}, {second.status_code}")


def _user_for_idempotency(prefix: str) -> str:
    from codeforge.services.auth_service import register_student

    user = register_student(f"{prefix}-{__import__('uuid').uuid4().hex[:8]}@example.com", "StrongPassword123", "Idem")
    return user.id


def idempotency_same_user(harness: EvalHarness, _case: dict[str, Any]) -> None:
    user_id = _user_for_idempotency("same")
    llm = _python_llm()
    with harness.sandbox_spy() as calls:
        _run_graph(harness, llm, "return one", user_id=user_id)
        _run_graph(harness, llm, "return one", user_id=user_id)
    if len(calls) != 1:
        raise AssertionError(f"expected 1 execution, saw {len(calls)}")


def idempotency_different_users(harness: EvalHarness, _case: dict[str, Any]) -> None:
    first = _user_for_idempotency("user-a")
    second = _user_for_idempotency("user-b")
    llm = _python_llm()
    with harness.sandbox_spy() as calls:
        _run_graph(harness, llm, "return one", user_id=first)
        _run_graph(harness, llm, "return one", user_id=second)
    if len(calls) != 2:
        raise AssertionError(f"different users shared an execution ({len(calls)})")


def idempotency_changed_code(harness: EvalHarness, _case: dict[str, Any]) -> None:
    user_id = _user_for_idempotency("code")
    with harness.sandbox_spy() as calls:
        _run_graph(harness, _python_llm(SAFE_CODE), "return one", user_id=user_id)
        _run_graph(
            harness,
            _python_llm("def solution():\n    return 2\n"),
            "return two",
            user_id=user_id,
        )
    if len(calls) != 2:
        raise AssertionError("changed code reused an execution")


def idempotency_changed_tests(harness: EvalHarness, _case: dict[str, Any]) -> None:
    user_id = _user_for_idempotency("tests")
    other_tests = "from solution import solution\n\ndef test_solution():\n    assert solution() == 1\n\ndef test_extra():\n    assert True\n"
    with harness.sandbox_spy() as calls:
        _run_graph(harness, _python_llm(tests=SAFE_TESTS), "return one", user_id=user_id)
        _run_graph(harness, _python_llm(tests=other_tests), "return one", user_id=user_id)
    if len(calls) != 2:
        raise AssertionError("changed tests reused an execution")


def route_python(harness: EvalHarness, _case: dict[str, Any]) -> None:
    with harness.sandbox_spy() as calls:
        result = _run_graph(harness, _python_llm(), "Write a Python function that returns 1")
    if result["report"].task_type != "python" or len(calls) != 1:
        raise AssertionError("python classification did not reach execution")


def route_sql(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from codeforge.evals.fakes import router_only

    with harness.sandbox_spy() as calls:
        result = _run_graph(harness, router_only("sql", "sql"), "Write an SQL query for top customers")
    if result["report"].status != "unsupported" or result["report"].code is not None or calls:
        raise AssertionError("SQL was treated as executable Python")


def route_other_language(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from codeforge.evals.fakes import router_only

    with harness.sandbox_spy() as calls:
        result = _run_graph(harness, router_only("other", "javascript"), "Write a JavaScript function")
    if result["report"].task_type != "other" or calls:
        raise AssertionError("an explicit non-Python language was executed as Python")


def route_default_contract(harness: EvalHarness, _case: dict[str, Any]) -> None:
    if 'default to "python"' not in ROUTER_SYSTEM_PROMPT:
        raise AssertionError("router prompt lost the python default")
    output = RouterOutput(
        task_type="python",
        language="python",
        description="coding task",
        confidence=0.8,
        reasoning="default",
    )
    if route_after_router({"router_output": output}) != "requirements":
        raise AssertionError("python classification did not continue to requirements")


def route_misleading_keywords(harness: EvalHarness, _case: dict[str, Any]) -> None:
    if "surface keywords" not in ROUTER_SYSTEM_PROMPT:
        raise AssertionError("router prompt no longer warns against keyword routing")
    with harness.sandbox_spy() as calls:
        result = _run_graph(
            harness,
            _python_llm(),
            "Write a Python function that builds an SQL query string",
        )
    if result["report"].task_type != "python" or len(calls) != 1:
        raise AssertionError("a misleading SQL mention overrode the python path")


def requirements_name_required(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    try:
        RequirementsOutput(
            task_type="python",
            language="python",
            description="missing name",
            return_type="int",
        )
    except ValidationError:
        return
    raise AssertionError("function name is optional")


def _requirements_report(harness: EvalHarness, **kwargs):
    with harness.sandbox_spy():
        result = _run_graph(harness, _python_llm(**kwargs), "extract requirements")
    return result["report"].requirements


def requirements_parameter(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from codeforge.models.schemas import ParameterSpec

    requirements = _requirements_report(
        harness,
        parameters=[ParameterSpec(name="items", data_type="list[int]", description="values")],
    )
    if requirements.parameters[0].name != "items":
        raise AssertionError("parameter name was not preserved")


def requirements_return(harness: EvalHarness, _case: dict[str, Any]) -> None:
    requirements = _requirements_report(harness, return_type="list[int]")
    if requirements.return_type != "list[int]":
        raise AssertionError("return type was not preserved")


def requirements_edges(harness: EvalHarness, _case: dict[str, Any]) -> None:
    requirements = _requirements_report(harness, edge_cases=["empty input"])
    if "empty input" not in requirements.edge_cases:
        raise AssertionError("edge case was dropped")


def requirements_constraints(harness: EvalHarness, _case: dict[str, Any]) -> None:
    requirements = _requirements_report(harness, constraints=["use a list comprehension"])
    if requirements.constraints != ["use a list comprehension"]:
        raise AssertionError("constraint was not preserved")


def requirements_multi(harness: EvalHarness, _case: dict[str, Any]) -> None:
    requirements = _requirements_report(
        harness,
        expected_behavior=["rejects negatives", "returns zero for empty input"],
    )
    if len(requirements.expected_behavior) != 2:
        raise AssertionError("multi-condition behavior was collapsed")


def requirements_algorithm(harness: EvalHarness, _case: dict[str, Any]) -> None:
    requirements = _requirements_report(harness, constraints=["sort with merge sort"])
    if "merge sort" not in requirements.constraints[0]:
        raise AssertionError("algorithmic constraint was lost")


def requirements_missing_optional(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    model = RequirementsOutput(
        task_type="python",
        language="python",
        function_name="solution",
        description="sparse",
        return_type="int",
    )
    if model.edge_cases or model.constraints or model.parameters:
        raise AssertionError("missing optional fields did not default to empty")


def reference_palindrome(harness: EvalHarness, case: dict[str, Any]) -> None:
    del harness
    text = case["input"]["text"]
    if is_palindrome(text) is not case["expected"]["palindrome"]:
        raise AssertionError("palindrome oracle mismatch")


def reference_factorial(harness: EvalHarness, case: dict[str, Any]) -> None:
    del harness
    if factorial(case["input"]["n"]) != case["expected"]["value"]:
        raise AssertionError("factorial oracle mismatch")


def reference_duplicates(harness: EvalHarness, case: dict[str, Any]) -> None:
    del harness
    if duplicates(case["input"]["values"]) != case["expected"]["duplicates"]:
        raise AssertionError("duplicates oracle mismatch")


def reference_clamp(harness: EvalHarness, case: dict[str, Any]) -> None:
    del harness
    payload = case["input"]
    if clamp(payload["value"], payload["low"], payload["high"]) != case["expected"]["value"]:
        raise AssertionError("clamp oracle mismatch")


def reference_div(harness: EvalHarness, case: dict[str, Any]) -> None:
    del harness
    payload = case["input"]
    if payload.get("raises"):
        try:
            safe_div(payload["numerator"], payload["denominator"])
        except ZeroDivisionError:
            return
        raise AssertionError("division by zero was not rejected")
    if safe_div(payload["numerator"], payload["denominator"]) != case["expected"]["value"]:
        raise AssertionError("division oracle mismatch")


def reference_factorial_invalid(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    try:
        factorial(-1)
    except ValueError:
        return
    raise AssertionError("negative factorial was accepted")


EXECUTORS: dict[str, Executor] = {
    "H-IDENTITY-001": identity_foreign_run,
    "H-IDENTITY-002": identity_foreign_execution,
    "H-IDENTITY-003": identity_self_approve_fixed,
    "H-IDENTITY-004": identity_role_claim,
    "H-IDENTITY-005": identity_instructor_operation,
    "H-IDENTITY-006": identity_identical_404,
    "H-PRIVACY-001": privacy_key("sk-synthetickey123456"),
    "H-PRIVACY-002": privacy_key("gsk_synthetickey123456"),
    "H-PRIVACY-003": privacy_key("ada.eval@example.com"),
    "H-PRIVACY-004": privacy_key("+919876543210"),
    "H-PRIVACY-005": privacy_key("234567890124"),
    "H-PRIVACY-006": privacy_key("4242424242424242"),
    "H-PRIVACY-007": privacy_benign,
    "H-PRIVACY-008": privacy_mixed,
    "H-POLICY-001": policy_subprocess,
    "H-POLICY-002": policy_os_remove,
    "H-POLICY-003": policy_open_waits,
    "H-POLICY-004": policy_safe_allow,
    "H-POLICY-005": policy_reject_skips_execution,
    "H-POLICY-006": policy_double_decision,
    "H-IDEM-001": idempotency_same_user,
    "H-IDEM-002": idempotency_different_users,
    "H-IDEM-003": idempotency_changed_code,
    "H-IDEM-004": idempotency_changed_tests,
    "S-ROUTE-001": route_python,
    "S-ROUTE-002": route_sql,
    "S-ROUTE-003": route_other_language,
    "S-ROUTE-004": route_default_contract,
    "S-ROUTE-005": route_misleading_keywords,
    "S-REQ-001": requirements_name_required,
    "S-REQ-002": requirements_parameter,
    "S-REQ-003": requirements_return,
    "S-REQ-004": requirements_edges,
    "S-REQ-005": requirements_constraints,
    "S-REQ-006": requirements_multi,
    "S-REQ-007": requirements_algorithm,
    "S-REQ-008": requirements_missing_optional,
    "S-REF-001": reference_palindrome,
    "S-REF-002": reference_factorial,
    "S-REF-003": reference_duplicates,
    "S-REF-004": reference_clamp,
    "S-REF-005": reference_div,
    "S-REF-006": reference_factorial_invalid,
    "S-REF-007": reference_palindrome,
    **R7_EXECUTORS,
    **R34_EXECUTORS,
}

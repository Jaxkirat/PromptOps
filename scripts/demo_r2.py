"""Eight R2 demonstrations.

Safe allow-class code runs on the explicit restricted-process backend when
Docker is down. That backend is not network or filesystem isolation. Docker
failures are reported as unavailable and do not execute the code.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_URL"] = "sqlite:///./demo_r2.sqlite"
os.environ["CODEFORGE_CHECKPOINT_PATH"] = "./demo_r2_checkpoints.sqlite"
os.environ.setdefault("CODEFORGE_SANDBOX_BACKEND", "restricted-process")

from codeforge.auth.identity import AuthenticatedPrincipal, principal_context
from codeforge.config.settings import get_settings
from codeforge.database.database import init_db
from codeforge.exceptions import ApprovalNotFoundError
from codeforge.graph.workflow import run_codeforge
from codeforge.models.schemas import CodeOutput, RequirementsOutput, RouterOutput, TestOutput
from codeforge.services.approval_service import create_approval, decide
from codeforge.services.auth_service import provision_instructor, register_student
from tests.conftest import FakeStructuredLLM


def llm(code: str, tests: str) -> FakeStructuredLLM:
    return FakeStructuredLLM(
        {
            RouterOutput: RouterOutput(
                task_type="python",
                language="python",
                description="python",
                confidence=0.9,
                reasoning="python",
            ),
            RequirementsOutput: RequirementsOutput(
                task_type="python",
                language="python",
                function_name="solution",
                description="demo",
                parameters=[],
                return_type="int",
                expected_behavior=["returns a value"],
                edge_cases=[],
                constraints=[],
            ),
            CodeOutput: CodeOutput(language="python", code=code, explanation=""),
            TestOutput: TestOutput(language="python", test_framework="pytest", test_code=tests),
        }
    )


def check(name: str, ok: bool, detail: str) -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


def main() -> None:
    init_db()
    settings = replace(get_settings(), sandbox_backend="restricted-process", sandbox_timeout_seconds=3)
    print("Demos use the local pytest runner. network_isolated must stay false.")
    results: list[bool] = []

    safe_code = "def solution(a, b):\n    return a + b\n"
    safe_tests = "from solution import solution\n\ndef test_add():\n    assert solution(1, 2) == 3\n"
    safe = run_codeforge("add", llm=llm(safe_code, safe_tests), settings=settings)
    execution = safe["report"].execution
    results.append(
        check(
            "1 safe allow",
            safe["report"].status == "success"
            and execution.executed
            and execution.exit_code == 0
            and execution.network_isolated is False
            and execution.sandbox_backend == "restricted-process",
            f"status={safe['report'].status} backend={execution.sandbox_backend} "
            f"network_isolated={execution.network_isolated} exit={execution.exit_code}",
        )
    )

    marker = Path("demo_r2_denied.txt")
    marker.unlink(missing_ok=True)
    denied_code = "import os\n\ndef solution():\n    os.system('echo denied')\n    return 1\n"
    denied = run_codeforge(
        "danger",
        llm=llm(denied_code, "from solution import solution\n\ndef test_s():\n    assert solution() == 1\n"),
        settings=settings,
    )
    results.append(
        check(
            "2 deny",
            denied["report"].status == "denied" and not denied["report"].execution.executed and not marker.exists(),
            denied["report"].status_detail,
        )
    )

    opened = Path("demo_r2_opened.txt")
    opened.unlink(missing_ok=True)
    file_code = f"def solution():\n    open(r'{opened}', 'w').write('x')\n    return 1\n"
    file_tests = "from solution import solution\n\ndef test_s():\n    assert solution() == 1\n"
    paused = run_codeforge("read", llm=llm(file_code, file_tests), settings=settings)
    results.append(
        check(
            "3 approval pause",
            paused.get("report") is None
            and paused.get("approval_interrupt")
            and paused["approval_interrupt"]["policy_decision"] == "needs_approval"
            and not opened.exists(),
            f"interrupt={paused.get('approval_interrupt')}",
        )
    )

    rejected = run_codeforge(
        "",
        llm=llm(file_code, file_tests),
        settings=settings,
        thread_id=paused["thread_id"],
        resume={"decision": "rejected", "actor_id": "demo-instructor"},
    )
    results.append(
        check(
            "4 rejection",
            rejected["report"].status == "rejected" and not rejected["report"].execution.executed and not opened.exists(),
            rejected["report"].status_detail,
        )
    )

    loop = run_codeforge(
        "loop",
        llm=llm(
            "def solution():\n    while True:\n        pass\n",
            "from solution import solution\n\ndef test_s():\n    solution()\n",
        ),
        settings=settings,
    )
    results.append(
        check(
            "5 timeout",
            loop["report"].status == "execution_timeout" and loop["report"].execution.timed_out,
            loop["report"].status_detail,
        )
    )

    suffix = uuid4().hex[:8]
    student = register_student(f"demo-r2-student-{suffix}@example.com", "StrongPassword123", "Demo Student")
    first = run_codeforge("add", llm=llm(safe_code, safe_tests), settings=settings, user_id=student.id)
    second = run_codeforge("add", llm=llm(safe_code, safe_tests), settings=settings, user_id=student.id)
    results.append(
        check(
            "6 idempotency",
            first["report"].execution.executed
            and second["report"].execution.idempotency_status == "hit"
            and second["report"].execution.executed is False,
            f"second_status={second['report'].execution.idempotency_status} executed={second['report'].execution.executed}",
        )
    )

    other = register_student(f"demo-r2-other-{suffix}@example.com", "StrongPassword123", "Other")
    approval_id = create_approval(
        user_id=student.id,
        run_id=None,
        thread_id="demo-thread",
        reasons=["open"],
        operations=["open"],
        code_text=file_code,
        tests_text=file_tests,
        summary="file read",
    )
    hidden = False
    try:
        with principal_context(
            AuthenticatedPrincipal(user_id=other.id, role="student", email=other.email, is_active=True)
        ):
            decide(approval_id, "approved")
    except ApprovalNotFoundError:
        hidden = True
    results.append(check("7 cross-user", hidden and not opened.exists(), "foreign student cannot decide"))

    print()
    print(f"{sum(results)}/{len(results)} demonstrations passed")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

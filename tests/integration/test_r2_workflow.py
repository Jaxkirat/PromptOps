"""LangGraph R2 branches: allow, deny, pause, reject, and no insecure fallback."""

from pathlib import Path

from codeforge.graph.workflow import run_codeforge
from codeforge.models.schemas import CodeOutput, RequirementsOutput, RouterOutput, TestOutput
from tests.conftest import FakeStructuredLLM


def _llm(code: str, tests: str) -> FakeStructuredLLM:
    return FakeStructuredLLM(
        {
            RouterOutput: RouterOutput(
                task_type="python",
                language="python",
                description="python function",
                confidence=0.9,
                reasoning="python",
            ),
            RequirementsOutput: RequirementsOutput(
                task_type="python",
                language="python",
                function_name="solution",
                description="solution",
                parameters=[],
                return_type="None",
                expected_behavior=["runs"],
                edge_cases=[],
                constraints=[],
            ),
            CodeOutput: CodeOutput(language="python", code=code, explanation=""),
            TestOutput: TestOutput(
                language="python", test_framework="pytest", test_code=tests
            ),
        }
    )


def test_safe_code_reaches_pytest(fake_llm_full_pipeline):
    result = run_codeforge("sum a list", llm=fake_llm_full_pipeline)
    report = result["report"]
    assert report.status == "success"
    assert report.tests_passed is True
    assert report.execution.executed is True
    assert report.execution.sandbox_backend == "restricted-process"
    assert report.execution.network_isolated is False
    assert result["approval_interrupt"] is None


def test_deny_does_not_execute(tmp_path: Path):
    marker = tmp_path / "denied.txt"
    code = (
        "import os\n"
        f"def solution():\n    os.system(r'type nul > {marker}')\n    return 1\n"
    )
    tests = "from solution import solution\n\ndef test_solution():\n    assert solution() == 1\n"
    result = run_codeforge("danger", llm=_llm(code, tests))
    assert result["report"].status == "denied"
    assert result["report"].execution.executed is False
    assert not marker.exists()


def test_file_access_pauses_and_rejection_does_not_run(tmp_path: Path):
    marker = tmp_path / "opened.txt"
    code = f"def solution():\n    open(r'{marker}', 'w').write('x')\n    return 1\n"
    tests = "from solution import solution\n\ndef test_solution():\n    assert solution() == 1\n"
    paused = run_codeforge("read a file", llm=_llm(code, tests))
    assert paused["approval_interrupt"] is not None
    assert paused["approval_interrupt"]["policy_decision"] == "needs_approval"
    assert paused.get("report") is None
    rejected = run_codeforge(
        "",
        llm=_llm(code, tests),
        thread_id=paused["thread_id"],
        resume={"decision": "rejected", "actor_id": "instructor-1"},
    )
    assert rejected["report"].status == "rejected"
    assert rejected["report"].execution.executed is False
    assert not marker.exists()


def test_approved_file_code_is_not_run_without_an_isolating_sandbox(tmp_path: Path):
    marker = tmp_path / "approved.txt"
    code = f"def solution():\n    open(r'{marker}', 'w').write('x')\n    return 1\n"
    tests = "from solution import solution\n\ndef test_solution():\n    assert solution() == 1\n"
    llm = _llm(code, tests)
    paused = run_codeforge("read a file", llm=llm)
    resumed = run_codeforge(
        "",
        llm=llm,
        thread_id=paused["thread_id"],
        resume={"decision": "approved", "actor_id": "instructor-1"},
    )
    assert resumed["report"].status == "unavailable"
    assert resumed["report"].execution.executed is False
    assert not marker.exists()

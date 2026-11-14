"""Builds and formats the structured final report for a CodeForge run.

Reporting is deliberately separate from execution: the reporter only inspects
the pipeline state (including the *actual* pytest execution result) and never
runs anything itself.
"""

from __future__ import annotations

from typing import Any, Mapping

from codeforge.models.schemas import (
    CodeOutput,
    ExecutionResult,
    FinalReport,
    RequirementsOutput,
    RouterOutput,
    TestOutput,
)


def build_report(state: Mapping[str, Any]) -> FinalReport:
    """Derive a :class:`FinalReport` from the pipeline state.

    The report honestly distinguishes generation success, execution success and
    test outcomes. Test results come exclusively from the real pytest run.
    """
    user_request: str = state.get("user_request", "")
    router: RouterOutput | None = state.get("router_output")
    requirements: RequirementsOutput | None = state.get("requirements_output")
    code: CodeOutput | None = state.get("code_output")
    tests: TestOutput | None = state.get("test_output")
    execution: ExecutionResult | None = state.get("execution_result")
    error: str | None = state.get("error")
    error_stage: str | None = state.get("error_stage")

    errors: list[str] = []
    if error:
        stage = f" (stage: {error_stage})" if error_stage else ""
        errors.append(f"{error}{stage}")

    generation_successful = code is not None and tests is not None
    execution_successful = execution is not None and execution.status in ("passed", "failed")
    tests_passed = execution is not None and execution.status == "passed"

    status: str
    detail: str

    if router is not None and router.task_type != "python":
        status = "unsupported"
        if router.task_type == "sql":
            detail = (
                "SQL request correctly identified, but SQL execution is not implemented "
                "in Phase 1 (planned: R7 Safe SQL Agent). No code was generated or executed."
            )
        else:
            detail = (
                f"Request classified as '{router.task_type}' "
                f"(language: {router.language}). Only Python tasks are supported in Phase 1."
            )
    elif error:
        status = "generation_error"
        detail = f"Pipeline failed before test execution completed: {error}"
    elif execution is None:
        status = "generation_error"
        detail = "Pipeline ended without executing the generated tests."
    elif execution.timed_out:
        status = "execution_timeout"
        detail = execution.error_message or "Test execution timed out."
    elif execution.status == "error":
        status = "execution_error"
        detail = execution.error_message or "Test execution failed to run correctly."
    elif execution.status == "failed":
        status = "tests_failed"
        detail = (
            f"Code and tests were generated, but {execution.failed_tests} of "
            f"{execution.total_tests} tests failed in actual pytest execution."
        )
    else:
        status = "success"
        detail = (
            f"All {execution.passed_tests} generated tests passed in actual pytest execution."
        )

    return FinalReport(
        user_request=user_request,
        status=status,  # type: ignore[arg-type]
        status_detail=detail,
        task_type=router.task_type if router else None,
        language=router.language if router else None,
        router_output=router,
        requirements=requirements,
        code=code,
        tests=tests,
        execution=execution,
        generation_successful=generation_successful,
        execution_successful=execution_successful,
        tests_passed=tests_passed,
        errors=errors,
    )


def format_report(report: FinalReport) -> str:
    """Render a human-readable report for the CLI."""
    line = "=" * 50
    parts: list[str] = [line, f"{'FINAL REPORT':^50}", line, ""]

    parts.append(f"Request:    {report.user_request}")
    parts.append(f"Task Type:  {report.task_type or 'unknown'}")
    parts.append(f"Language:   {report.language or 'unknown'}")
    parts.append(f"Status:     {report.status.upper()}")
    parts.append(f"Detail:     {report.status_detail}")

    if report.requirements is not None:
        req = report.requirements
        parts += ["", "-" * 50, "Extracted Requirements:", f"  Function: {req.function_name}"]
        for param in req.parameters:
            parts.append(f"  Param:    {param.name}: {param.data_type}")
        parts.append(f"  Returns:  {req.return_type}")
        if req.constraints:
            parts.append("  Constraints:")
            parts += [f"    - {c}" for c in req.constraints]
        if req.implementation_notes:
            parts.append("  Assumptions / notes:")
            parts += [f"    - {n}" for n in req.implementation_notes]

    if report.code is not None:
        parts += ["", "-" * 50, "Generated Code:", "", report.code.code]

    if report.tests is not None:
        parts += ["", "-" * 50, "Generated Tests:", "", report.tests.test_code]

    if report.execution is not None:
        ex = report.execution
        parts += ["", "-" * 50, "Test Results (actual pytest execution):"]
        parts.append(
            f"  {ex.passed_tests} passed, {ex.failed_tests} failed, "
            f"{ex.skipped_tests} skipped (exit code: {ex.exit_code})"
        )
        parts.append(f"  Execution Time: {ex.execution_time_seconds:.2f}s")
        if ex.timed_out:
            parts.append("  TIMED OUT")
        if ex.error_message:
            parts.append(f"  Note: {ex.error_message}")

    if report.errors:
        parts += ["", "-" * 50, "Errors:"]
        parts += [f"  - {err}" for err in report.errors]

    parts += ["", line]
    return "\n".join(parts)

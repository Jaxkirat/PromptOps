"""Sample requests for demonstrating CodeForge.

Run (with credentials configured in .env):

    python -m examples.sample_requests
"""

from __future__ import annotations

SAMPLE_REQUESTS: list[str] = [
    # Flagship Phase 1 scenario
    "If I pass a list, return its sum using a list comprehension; "
    "if a tuple, use functional programming.",
    # Simple Python tasks
    "Write a function that checks whether a string is a palindrome.",
    "Write a function that computes the factorial of a non-negative integer.",
    "Write a function that returns the first n Fibonacci numbers as a list.",
    # Honestly reported as not implemented in Phase 1
    "Write an SQL query that returns the top 5 customers by total order value.",
    # Not a coding task
    "What is the capital of France?",
]


def main() -> None:
    from codeforge.graph.workflow import run_codeforge

    for request in SAMPLE_REQUESTS:
        print("\n" + "#" * 70)
        print(f"# REQUEST: {request}")
        print("#" * 70)
        result = run_codeforge(request)
        report = result.get("report")
        if report is None:
            print("No report produced.")
            continue
        print(f"Status: {report.status} — {report.status_detail}")
        if report.execution is not None:
            print(
                f"Tests:  {report.execution.passed_tests} passed, "
                f"{report.execution.failed_tests} failed"
            )


if __name__ == "__main__":
    main()

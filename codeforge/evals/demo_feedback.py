"""Reproducible thumbs-down flywheel.

The candidate fails against an isolated buggy classifier, then passes against
the fixed classifier. Production routing is not changed. Temporary feedback
rows and the pending case file are deleted before exit.
"""

from __future__ import annotations

from codeforge.auth.identity import AuthenticatedPrincipal, principal_context
from codeforge.evals.feedback_to_golden import feedback_to_case, load_pending, write_pending
from codeforge.evals.flywheel_subject import classify_label, classify_label_fixed
from codeforge.evals.harness import EvalHarness
from codeforge.services.feedback_service import submit_feedback

SAMPLE = "Write a Python function that builds a query string"


def _evaluate(label_fn, text: str, expected: str) -> tuple[bool, str]:
    actual = label_fn(text)
    return actual == expected, actual


def main() -> int:
    print("THUMBS-DOWN FEEDBACK FLYWHEEL")
    pending_path = None
    try:
        with EvalHarness() as harness:
            token, user_id = harness.register_student("flywheel")
            run = harness.submit(token, SAMPLE)
            email = "flywheel@example.com"
            del email
            with principal_context(
                AuthenticatedPrincipal(
                    user_id=user_id,
                    role="student",
                    email="flywheel@example.com",
                    is_active=True,
                )
            ):
                feedback = submit_feedback(
                    run["id"],
                    "down",
                    "It treated a Python function as SQL because the request mentioned a query.",
                )
            print(f"Recorded thumbs-down {feedback.id} for run {feedback.run_id}")
            case = feedback_to_case(
                feedback.id,
                expected={"label": "python"},
                case_input={"text": SAMPLE},
                description="A Python function that builds a query string stays on the Python path",
                category="routing",
            )
            pending_path = write_pending(case)
            loaded = load_pending(pending_path)
            print(f"Candidate golden case {loaded.id} written to {pending_path}")
            if loaded.expected.get("label") == run["status"]:
                print("Refusing to use the model status as the oracle.")
                return 1

            matched, actual = _evaluate(classify_label, SAMPLE, "python")
            print("INITIAL EVALUATION: FAIL" if not matched else "INITIAL EVALUATION: PASS")
            print("Expected: python")
            print(f"Actual: {actual}")
            if matched:
                print("The candidate was expected to fail before the fix.")
                return 1

            fixed, fixed_actual = _evaluate(classify_label_fixed, SAMPLE, "python")
            print("APPLYING FIX in the isolated flywheel subject...")
            print("RE-EVALUATION: PASS" if fixed else "RE-EVALUATION: FAIL")
            print("Expected: python")
            print(f"Actual: {fixed_actual}")
            if not fixed:
                return 1
            print("CANDIDATE: PASS")
            print("Production router was not modified. Pending file will be removed.")
    finally:
        if pending_path is not None and pending_path.exists():
            pending_path.unlink()
            print(f"Removed {pending_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

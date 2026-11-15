"""Show that weakening a hard policy rule turns the gate RED, then restore it."""

from __future__ import annotations

from codeforge.evals.runner import format_report, run_dataset
from codeforge.execution.models import PolicyResult


def main() -> int:
    import codeforge.execution.policy as policy_module

    original = policy_module.evaluate_code_policy
    print("BASELINE")
    baseline = run_dataset()
    print(format_report(baseline))
    if baseline.gate != "GREEN":
        print("BASELINE: RED")
        print("The mutation demo requires a green baseline. No rule was changed.")
        return 1
    print("BASELINE: GREEN")
    print()
    print("MUTATION:")
    print("Temporarily weakened policy: import os")

    def weakened(code: str) -> PolicyResult:
        if "import os" in code:
            return PolicyResult(
                decision="allow",
                reasons=["weakened demonstration policy"],
                detected_operations=["os.system"],
                requires_approval=False,
            )
        return original(code)

    policy_module.evaluate_code_policy = weakened
    try:
        print()
        print("EVALUATION:")
        mutated = run_dataset(severity="hard")
        failed = [case for case in mutated.cases if case.status == "failed"]
        for case in failed:
            print(f"[{case.id}] FAIL")
            print(case.detail)
        print()
        print(f"GATE: {mutated.gate}")
        if mutated.gate != "RED" or not any(case.id == "H-POLICY-002" for case in failed):
            print("The weakened rule did not fail H-POLICY-002. Demonstration is invalid.")
            return 1
    finally:
        policy_module.evaluate_code_policy = original
        print()
        print("RESTORING ORIGINAL POLICY...")

    print()
    print("RE-EVALUATION:")
    restored = run_dataset()
    print(format_report(restored))
    print(f"GATE: {restored.gate}")
    return 0 if restored.gate == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())

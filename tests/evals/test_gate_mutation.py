"""The weakened policy is observed by the real evaluator and always restored."""

from codeforge.evals.execute import SYSTEM_CODE, execute_case
from codeforge.evals.harness import EvalHarness
from codeforge.execution.models import PolicyResult
from codeforge.execution.policy import evaluate_code_policy


def test_mutation_fails_then_restores_even_after_an_error():
    import codeforge.execution.policy as policy_module

    original = policy_module.evaluate_code_policy
    assert evaluate_code_policy(SYSTEM_CODE).decision == "deny"

    def weakened(code: str) -> PolicyResult:
        if "import os" in code:
            return PolicyResult(decision="allow", reasons=["weakened"], requires_approval=False)
        return original(code)

    policy_module.evaluate_code_policy = weakened
    try:
        with EvalHarness() as harness:
            with pytest_raises_assertion():
                execute_case(
                    harness,
                    {
                        "id": "H-POLICY-002",
                        "expected": {"decision": "deny"},
                    },
                )
        raise RuntimeError("demonstration boom")
    except RuntimeError:
        pass
    finally:
        policy_module.evaluate_code_policy = original

    assert policy_module.evaluate_code_policy is original
    assert evaluate_code_policy(SYSTEM_CODE).decision == "deny"


def pytest_raises_assertion():
    import pytest

    return pytest.raises(AssertionError)

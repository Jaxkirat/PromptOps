"""Run a verified template through the existing policy check and sandbox."""

from __future__ import annotations

from codeforge.execution.policy import combine_policies, evaluate_code_policy
from codeforge.execution.reporter import build_report
from codeforge.execution.sandbox import run_sandbox
from codeforge.models.schemas import CodeOutput, ExecutionResult, RequirementsOutput, RouterOutput, TestOutput
from codeforge.templates.library import TemplateMatch


def run_template(request: str, match: TemplateMatch) -> dict:
    code_policy = evaluate_code_policy(match.code)
    test_policy = evaluate_code_policy(match.tests)
    policy = combine_policies(code_policy, test_policy)
    if policy.decision == "deny":
        execution = ExecutionResult(
            status="denied",
            executed=False,
            policy_decision="deny",
            policy_reasons=policy.reasons,
            error_message="Template blocked by policy.",
        )
    elif policy.decision == "needs_approval":
        execution = ExecutionResult(
            status="awaiting_approval",
            executed=False,
            policy_decision="needs_approval",
            policy_reasons=policy.reasons,
            error_message="Template requires approval.",
        )
    else:
        execution = run_sandbox(match.code, match.tests, policy)
    state = {
        "user_request": request,
        "router_output": RouterOutput(
            task_type="python",
            language="python",
            description=match.name,
            confidence=1.0,
            reasoning="Verified template.",
        ),
        "requirements_output": RequirementsOutput(
            task_type="python",
            language="python",
            function_name=match.template_id.lower(),
            description=match.name,
            parameters=[],
            return_type="varies",
            expected_behavior=[match.variation],
            edge_cases=[],
            constraints=[],
        ),
        "code_output": CodeOutput(language="python", code=match.code, explanation=match.name),
        "test_output": TestOutput(language="python", test_framework="pytest", test_code=match.tests),
        "execution_result": execution,
    }
    report = build_report(state)
    return {
        "report": report,
        "resilience": {
            "template_hit": True,
            "template_id": match.template_id,
            "template_version": match.version,
            "generation_source": "template",
            "provider": "",
            "model": "",
            "fallback_used": False,
            "provider_attempts": [],
        },
    }

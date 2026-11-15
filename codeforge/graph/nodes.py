"""LangGraph node implementations.

Each node wraps exactly one agent (or the runner/reporter) and returns a
partial state update. Agent failures are captured into ``error`` /
``error_stage`` so the graph can route to the report node instead of crashing.
"""

from __future__ import annotations

import logging

from codeforge.agents.code_generation_agent import CodeGenerationAgent
from codeforge.agents.requirements_agent import RequirementsAgent
from codeforge.agents.router_agent import RouterAgent
from codeforge.agents.test_generation_agent import TestGenerationAgent
from codeforge.config.settings import Settings, get_settings
from codeforge.exceptions import CodeForgeError
from codeforge.execution.idempotency import (
    claim_execution,
    idempotency_key,
    lookup_execution,
    result_from_record,
    store_result,
)
from codeforge.execution.policy import combine_policies, evaluate_code_policy
from codeforge.execution.reporter import build_report
from codeforge.execution.runner import PytestRunner
from codeforge.execution.sandbox import run_sandbox
from codeforge.graph.state import CodeForgeState
from codeforge.models.schemas import ExecutionResult

logger = logging.getLogger(__name__)


class GraphNodes:
    """Bundles the node callables with their agent/runner dependencies."""

    def __init__(
        self,
        router_agent: RouterAgent,
        requirements_agent: RequirementsAgent,
        code_generation_agent: CodeGenerationAgent,
        test_generation_agent: TestGenerationAgent,
        runner: PytestRunner,
        settings: Settings | None = None,
    ) -> None:
        self._router = router_agent
        self._requirements = requirements_agent
        self._code_generation = code_generation_agent
        self._test_generation = test_generation_agent
        # Kept so existing callers can still construct GraphNodes. Production
        # execution goes through the R2 sandbox, not this runner.
        self._runner = runner
        self._settings = settings or get_settings()

    # -- Agent nodes -------------------------------------------------------

    def router_node(self, state: CodeForgeState) -> CodeForgeState:
        try:
            return {"router_output": self._router.run(state["user_request"])}
        except CodeForgeError as exc:
            return _failure("router", exc)

    def requirements_node(self, state: CodeForgeState) -> CodeForgeState:
        try:
            router_output = state["router_output"]
            assert router_output is not None
            return {
                "requirements_output": self._requirements.run(
                    state["user_request"], router_output
                )
            }
        except CodeForgeError as exc:
            return _failure("requirements", exc)

    def code_generation_node(self, state: CodeForgeState) -> CodeForgeState:
        try:
            requirements = state["requirements_output"]
            assert requirements is not None
            return {"code_output": self._code_generation.run(requirements)}
        except CodeForgeError as exc:
            return _failure("code_generation", exc)

    def test_generation_node(self, state: CodeForgeState) -> CodeForgeState:
        try:
            requirements = state["requirements_output"]
            code = state["code_output"]
            assert requirements is not None and code is not None
            return {"test_output": self._test_generation.run(requirements, code)}
        except CodeForgeError as exc:
            return _failure("test_generation", exc)

    # -- R2 policy, approval and sandbox -----------------------------------

    def policy_node(self, state: CodeForgeState) -> CodeForgeState:
        code = state.get("code_output")
        tests = state.get("test_output")
        if code is None or tests is None:
            return _failure("policy", CodeForgeError("Code and tests are required before policy."))
        policy = combine_policies(
            evaluate_code_policy(code.code), evaluate_code_policy(tests.test_code)
        )
        user_id = state.get("user_id") or ""
        key = idempotency_key(user_id, code.code, tests.test_code) if user_id else ""
        logger.info(
            "policy_decision decision=%s operations=%s user_id=%s",
            policy.decision,
            ",".join(policy.detected_operations) or "none",
            user_id or "anonymous",
        )
        update: CodeForgeState = {
            "policy_result": policy.model_dump(),
            "policy_decision": policy.decision,
            "approval_required": policy.requires_approval,
            "idempotency_key": key or None,
            "idempotency_hit": False,
        }
        if user_id:
            existing = lookup_execution(user_id, key)
            if existing is None:
                existing, created = claim_execution(
                    user_id=user_id,
                    key=key,
                    state="pending" if policy.decision == "needs_approval" else "started",
                    policy_decision=policy.decision,
                    reasons=policy.reasons,
                )
                if created:
                    return update
            stored = result_from_record(existing) if existing is not None else None
            if stored is None:
                pending = existing is not None and existing.state == "pending"
                stored = ExecutionResult(
                    status="awaiting_approval" if pending else "unavailable",
                    executed=False,
                    policy_decision=(existing.policy_decision if existing else policy.decision),
                    error_message=(
                        "Execution paused: human approval required."
                        if pending
                        else "An identical request is already recorded and was not executed again."
                    ),
                    idempotency_status="hit",
                )
            stored.idempotency_status = "hit"
            stored.executed = False
            logger.info(
                "idempotency_hit user_id=%s state=%s",
                user_id,
                existing.state if existing is not None else "unknown",
            )
            update["idempotency_hit"] = True
            update["execution_result"] = stored
            if existing is not None:
                update["policy_decision"] = existing.policy_decision or policy.decision
            return update
        return update

    def blocked_node(self, state: CodeForgeState) -> CodeForgeState:
        policy = state.get("policy_result") or {}
        reasons = policy.get("reasons") or ["Execution blocked by CodeForge security policy."]
        result = ExecutionResult(
            status="denied",
            executed=False,
            policy_decision="deny",
            policy_reasons=list(reasons),
            error_message="Execution blocked by CodeForge security policy. " + " ".join(reasons),
            idempotency_status="created",
        )
        _persist(state, "denied", result)
        logger.info("policy_denied user_id=%s", state.get("user_id") or "anonymous")
        return {"execution_result": result, "policy_decision": "deny"}

    def approval_node(self, state: CodeForgeState) -> CodeForgeState:
        from langgraph.types import interrupt

        policy = state.get("policy_result") or {}
        decision = interrupt(
            {
                "policy_decision": "needs_approval",
                "reasons": policy.get("reasons") or [],
                "operations": policy.get("detected_operations") or [],
                "thread_id": state.get("thread_id"),
            }
        )
        status = "approved" if isinstance(decision, dict) and decision.get("decision") == "approved" else "rejected"
        actor = decision.get("actor_id") if isinstance(decision, dict) else None
        if status != "approved":
            result = ExecutionResult(
                status="rejected",
                executed=False,
                policy_decision="needs_approval",
                policy_reasons=list(policy.get("reasons") or []),
                approval_status="rejected",
                error_message="Execution was rejected and was not run.",
            )
            _persist(state, "rejected", result)
            logger.info("approval_rejected actor_id=%s", actor)
            return {
                "approval_status": "rejected",
                "approval_actor_id": actor,
                "execution_result": result,
            }
        logger.info("approval_granted actor_id=%s", actor)
        return {"approval_status": "approved", "approval_actor_id": actor}

    def execution_node(self, state: CodeForgeState) -> CodeForgeState:
        code = state["code_output"]
        tests = state["test_output"]
        assert code is not None and tests is not None
        policy = combine_policies(
            evaluate_code_policy(code.code), evaluate_code_policy(tests.test_code)
        )
        if policy.decision == "deny":
            result = ExecutionResult(
                status="denied",
                executed=False,
                policy_decision="deny",
                policy_reasons=policy.reasons,
                error_message="Execution blocked by CodeForge security policy. " + " ".join(policy.reasons),
            )
            _persist(state, "denied", result)
            return {"execution_result": result, "policy_decision": "deny", "policy_result": policy.model_dump()}
        approved = state.get("approval_status") == "approved"
        if policy.decision == "needs_approval" and not approved:
            result = _policy_result(
                "awaiting_approval",
                policy,
                "Execution paused: human approval required.",
                approval_status="pending",
            )
            _persist(state, "pending", result)
            return {"execution_result": result, "policy_decision": policy.decision}
        try:
            result = run_sandbox(
                code.code,
                tests.test_code,
                policy,
                approved=approved,
                settings=self._settings,
            )
        except Exception as exc:  # noqa: BLE001 - sandbox failures become state
            logger.exception("Sandbox raised unexpectedly")
            return _failure("execution", exc)
        result.policy_decision = policy.decision
        result.policy_reasons = policy.reasons
        result.approval_status = state.get("approval_status")
        terminal = {
            "passed": "passed",
            "failed": "failed",
            "timeout": "timeout",
            "error": "unavailable",
            "unavailable": "unavailable",
        }.get(result.status, result.status)
        _persist(state, terminal, result)
        logger.info(
            "execution_finished status=%s exit=%s backend=%s",
            result.status,
            result.exit_code,
            result.sandbox_backend,
        )
        return {
            "execution_result": result,
            "policy_decision": policy.decision,
            "policy_result": policy.model_dump(),
        }

    # -- Report node -------------------------------------------------------

    def report_node(self, state: CodeForgeState) -> CodeForgeState:
        return {"report": build_report(state)}


def _failure(stage: str, exc: Exception) -> CodeForgeState:
    logger.error("Stage '%s' failed: %s", stage, exc)
    return {"error": str(exc), "error_stage": stage}


def _policy_result(status: str, policy, message: str, approval_status: str | None) -> ExecutionResult:
    return ExecutionResult(
        status=status,  # type: ignore[arg-type]
        executed=False,
        policy_decision=policy.decision,
        policy_reasons=list(policy.reasons),
        approval_status=approval_status,
        error_message=message,
    )


def _persist(state: CodeForgeState, record_state: str, result: ExecutionResult) -> None:
    user_id = state.get("user_id") or ""
    key = state.get("idempotency_key") or ""
    if user_id and key:
        store_result(user_id, key, record_state, result)

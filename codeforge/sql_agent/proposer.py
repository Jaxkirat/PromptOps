"""SQL proposers.

The fixture proposer is the default used by tests, CI and the demo. It does not
call a live model. A live proposer uses the existing provider settings and still
cannot execute anything: the service validates every proposal.
"""

from __future__ import annotations

import re
from typing import Protocol

from codeforge.sql_agent.models import SqlProposal

_SQL_START = re.compile(
    r"^(with|select|insert|update|delete|drop|alter|create|attach|detach|pragma|"
    r"replace|vacuum|begin|grant|revoke|truncate)\b",
    re.IGNORECASE,
)


class SqlProposer(Protocol):
    def propose(self, question: str, schema_context: str, mode: str) -> SqlProposal | None:
        """Return a proposal, or None when no query should be invented."""


def looks_like_sql(question: str) -> bool:
    """True when the question itself is a SQL statement rather than prose."""
    return bool(_SQL_START.match((question or "").strip()))


class FixtureSqlProposer:
    """Deterministic stand-in. SQL-shaped questions are echoed so attacks reach the validator."""

    def propose(self, question: str, schema_context: str, mode: str) -> SqlProposal | None:
        del schema_context
        text = (question or "").strip().rstrip(";")
        if looks_like_sql(text):
            return SqlProposal(sql=text, parameters=[], explanation="")
        lowered = text.lower()
        if mode == "instructor_ticket":
            if "failing test" in lowered or "which test failed" in lowered:
                sql = "SELECT ticket_ref, last_failing_test, sanitised_request FROM ticket_handoff_context"
            elif "generated code" in lowered:
                sql = "SELECT run_id, created_at, generated_code FROM student_generated_code ORDER BY created_at DESC"
            elif "original request" in lowered or "handoff" in lowered:
                sql = "SELECT ticket_ref, sanitised_request, handoff_summary, last_failing_test FROM ticket_handoff_context"
            elif any(phrase in lowered for phrase in ("attempt", "execution history", "previous")):
                sql = (
                    "SELECT ticket_ref, run_id, status, generated_code, error_summary "
                    "FROM ticket_repair_history ORDER BY created_at"
                )
            else:
                return None
            return SqlProposal(sql=sql, parameters=[], explanation="")
        if any(phrase in lowered for phrase in ("last 10 prompts", "previous prompts", "my prompts", "what did i ask")):
            sql = (
                "SELECT run_id, created_at, prompt FROM student_prompt_history "
                "ORDER BY created_at DESC LIMIT 10"
            )
        elif "failed" in lowered:
            sql = (
                "SELECT run_id, created_at, status, error_summary FROM student_execution_results "
                "WHERE status != 'success' ORDER BY created_at DESC"
            )
        elif "generated code" in lowered:
            sql = (
                "SELECT run_id, created_at, generated_code FROM student_generated_code "
                "ORDER BY created_at DESC"
            )
        elif "execution" in lowered or "error in my" in lowered or "previous execution" in lowered:
            sql = (
                "SELECT run_id, status, policy_decision, error_summary "
                "FROM student_execution_results ORDER BY created_at DESC"
            )
        elif "how many" in lowered or "count my" in lowered or "attempt" in lowered:
            sql = "SELECT COUNT(*) AS total FROM student_run_history"
        else:
            return None
        return SqlProposal(sql=sql, parameters=[], explanation="")


class FixedSqlProposer:
    """Test double that always proposes one statement."""

    def __init__(self, sql: str, parameters: list | None = None) -> None:
        self._sql = sql
        self._parameters = list(parameters or [])

    def propose(self, question: str, schema_context: str, mode: str) -> SqlProposal | None:
        del question, schema_context, mode
        return SqlProposal(sql=self._sql, parameters=list(self._parameters), explanation="")


class LiveSqlProposer:
    """Optional live model. Missing credentials become a generation failure, not a pass."""

    def propose(self, question: str, schema_context: str, mode: str) -> SqlProposal | None:
        from codeforge.models.llm_factory import create_llm

        llm = create_llm()
        prompt = (
            "Propose one SQLite SELECT query as structured data. "
            "Do not choose a user id, ticket owner, or role. "
            "The server has already restricted the rows. "
            f"Access mode: {mode}. "
            f"Allowed schema:\n{schema_context}\n"
            f"Question: {question}"
        )
        try:
            proposal = llm.with_structured_output(SqlProposal).invoke(prompt)
        except Exception:
            return None
        if isinstance(proposal, SqlProposal):
            return proposal
        if isinstance(proposal, dict):
            return SqlProposal.model_validate(proposal)
        return None


_proposer: SqlProposer | None = None


def get_sql_proposer() -> SqlProposer:
    if _proposer is not None:
        return _proposer
    from codeforge.config.settings import get_settings

    if get_settings().sql_proposer == "live":
        return LiveSqlProposer()
    return FixtureSqlProposer()


def set_sql_proposer(proposer: SqlProposer | None) -> None:
    global _proposer
    _proposer = proposer

"""SQL agent HTTP API. Identity comes from the bearer token only."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from codeforge.api.dependencies import get_current_principal
from codeforge.auth.identity import AuthenticatedPrincipal
from codeforge.config.settings import get_settings
from codeforge.exceptions import SqlAgentDisabledError
from codeforge.sql_agent.models import SqlAnswer, SqlQueryRequest
from codeforge.sql_agent.service import ask_sql, list_ticket_overview, ticket_context

router = APIRouter(prefix="/sql", tags=["sql"])


def _require_enabled() -> None:
    if not get_settings().sql_agent_enabled:
        raise SqlAgentDisabledError(
            "The SQL agent is disabled. Set CODEFORGE_SQL_AGENT_ENABLED=true to use it."
        )


@router.post("/query", response_model=SqlAnswer)
def query_sql(
    payload: SqlQueryRequest,
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> SqlAnswer:
    _require_enabled()
    return ask_sql(payload.question, payload.ticket_id)


@router.get("/tickets")
def assigned_tickets(
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    _require_enabled()
    return list_ticket_overview()


@router.get("/tickets/{ticket_id}")
def assigned_ticket(
    ticket_id: str,
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    _require_enabled()
    return ticket_context(ticket_id)

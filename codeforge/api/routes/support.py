"""Student and instructor support tickets."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from codeforge.api.dependencies import get_current_principal
from codeforge.auth.identity import AuthenticatedPrincipal
from codeforge.escalation.service import get_ticket, list_my_tickets, post_reply

router = APIRouter(prefix="/support/tickets", tags=["support"])


class ReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.get("")
def tickets(_principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> dict:
    return {"tickets": list_my_tickets()}


@router.get("/{ticket_id}")
def ticket(ticket_id: str, _principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> dict:
    return get_ticket(ticket_id)


@router.post("/{ticket_id}/replies")
def reply(
    ticket_id: str,
    payload: ReplyRequest,
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    return post_reply(ticket_id, payload.message)

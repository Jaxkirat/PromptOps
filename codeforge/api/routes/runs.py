"""Run endpoints: submission, history and single-run retrieval.

Ownership always comes from the authenticated token. The service functions
take no user id; cross-user access is indistinguishable from a missing run
(identical 404).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from codeforge.api.dependencies import get_current_principal
from codeforge.api.schemas.run import RunListResponse, RunSubmitRequest
from codeforge.auth.identity import AuthenticatedPrincipal
from codeforge.services.run_service import RunRecord, get_my_runs, get_run, submit_code_request
from codeforge.services.feedback_service import FeedbackRecord, get_feedback_for_run, submit_feedback

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunRecord, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: RunSubmitRequest,
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> RunRecord:
    """Authenticate -> mask PII/secrets -> reserve quota -> run CodeForge ->
    persist sanitized output -> return structured results."""
    return submit_code_request(payload.request, payload.conversation_id)


@router.get("", response_model=RunListResponse)
def list_runs(
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> RunListResponse:
    runs = get_my_runs()
    return RunListResponse(runs=runs, total=len(runs))


@router.get("/{run_id}", response_model=RunRecord)
def get_single_run(
    run_id: str,
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> RunRecord:
    return get_run(run_id)


class FeedbackRequest(BaseModel):
    vote: str = Field(pattern="^(up|down)$")
    explanation: str = Field(default="", max_length=2000)


@router.post("/{run_id}/feedback", response_model=FeedbackRecord, status_code=status.HTTP_201_CREATED)
def create_feedback(
    run_id: str,
    payload: FeedbackRequest,
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> FeedbackRecord:
    return submit_feedback(run_id, payload.vote, payload.explanation)


@router.get("/{run_id}/feedback", response_model=FeedbackRecord)
def read_feedback(
    run_id: str,
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> FeedbackRecord:
    return get_feedback_for_run(run_id)

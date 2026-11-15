"""R2 approval and execution-report endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from codeforge.api.dependencies import get_current_principal
from codeforge.auth.identity import AuthenticatedPrincipal
from codeforge.services.approval_service import decide, get_approval, list_pending
from codeforge.services.run_service import get_run

router = APIRouter(tags=["approvals"])


class ApprovalDecision(BaseModel):
    confirm: bool = Field(description="Must be true. The UI requires an explicit confirmation.")


@router.get("/runs/{run_id}/execution")
def get_execution(
    run_id: str,
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    """Stored execution report for a run the caller owns. No re-execution."""
    run = get_run(run_id)
    artifacts = run.artifacts or {}
    return {
        "run_id": run.id,
        "status": run.status,
        "policy_decision": artifacts.get("policy_decision"),
        "policy_reasons": artifacts.get("policy_reasons") or [],
        "approval_status": artifacts.get("approval_status"),
        "sandbox_backend": artifacts.get("sandbox_backend"),
        "network_isolated": artifacts.get("network_isolated"),
        "filesystem_isolated": artifacts.get("filesystem_isolated"),
        "idempotency_status": artifacts.get("idempotency_status"),
        "executed": artifacts.get("executed"),
        "pytest_exit_code": artifacts.get("exit_code"),
        "tests": run.test_results,
        "timed_out": artifacts.get("timed_out"),
        "stdout": artifacts.get("stdout") or "",
        "stderr": artifacts.get("stderr") or "",
        "error_message": artifacts.get("error_message"),
        "duration_seconds": run.execution_time,
    }


@router.get("/approvals/pending")
def pending_approvals(
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    rows = list_pending()
    return {"approvals": rows, "total": len(rows)}


@router.get("/approvals/{approval_id}")
def read_approval(
    approval_id: str,
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    return get_approval(approval_id)


@router.post("/approvals/{approval_id}/approve")
def approve(
    approval_id: str,
    payload: ApprovalDecision,
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    if not payload.confirm:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="Confirmation is required.")
    return decide(approval_id, "approved")


@router.post("/approvals/{approval_id}/reject", status_code=status.HTTP_200_OK)
def reject(
    approval_id: str,
    payload: ApprovalDecision,
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    if not payload.confirm:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="Confirmation is required.")
    return decide(approval_id, "rejected")

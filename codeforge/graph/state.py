"""Typed state shared across the LangGraph workflow."""

from __future__ import annotations

from typing import Optional, TypedDict

from codeforge.models.schemas import (
    CodeOutput,
    ExecutionResult,
    FinalReport,
    RequirementsOutput,
    RouterOutput,
    TestOutput,
)


class CodeForgeState(TypedDict, total=False):
    """State carried through the pipeline.

    Every node reads the fields it needs and returns a partial update.
    ``error`` / ``error_stage`` propagate failures to the report node without
    aborting the graph, so the caller always receives a structured report.
    """

    # Input
    user_request: str

    # Agent outputs
    router_output: Optional[RouterOutput]
    requirements_output: Optional[RequirementsOutput]
    code_output: Optional[CodeOutput]
    test_output: Optional[TestOutput]

    # Execution and reporting
    execution_result: Optional[ExecutionResult]
    report: Optional[FinalReport]

    # Error propagation
    error: Optional[str]
    error_stage: Optional[str]

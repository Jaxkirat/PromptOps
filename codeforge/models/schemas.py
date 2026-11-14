"""Pydantic structured-output schemas shared across the CodeForge pipeline.

Every agent returns one of these validated models instead of free-form text.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

_CODE_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_+-]*\s*\n(.*?)\n?\s*```\s*$", re.DOTALL)


def strip_markdown_fences(text: str) -> str:
    """Remove a single wrapping Markdown code fence from ``text`` if present."""
    match = _CODE_FENCE_RE.match(text)
    if match:
        return match.group(1).strip("\n")
    return text


class RouterOutput(BaseModel):
    """Classification of the incoming natural-language request."""

    task_type: Literal["python", "sql", "other"] = Field(
        description="Category of the request: python, sql, or other."
    )
    language: str = Field(description="Detected programming language or 'none'.")
    description: str = Field(description="Short summary of what the user asked for.")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Classification confidence between 0 and 1."
    )
    reasoning: str = Field(description="Why the request was classified this way.")


class ParameterSpec(BaseModel):
    """Specification of a single function parameter."""

    name: str = Field(description="Parameter name.")
    data_type: str = Field(description="Expected data type, e.g. 'list[int]'.")
    description: str = Field(default="", description="What the parameter represents.")
    required: bool = Field(default=True, description="Whether the parameter is required.")


class RequirementsOutput(BaseModel):
    """Structured programming requirements extracted from the user request."""

    task_type: str = Field(description="Task type inherited from the router.")
    language: str = Field(description="Target programming language.")
    function_name: str = Field(description="Snake_case name for the function to implement.")
    description: str = Field(description="What the function must do.")
    parameters: list[ParameterSpec] = Field(
        default_factory=list, description="Function parameters."
    )
    return_type: str = Field(description="Expected return type.")
    expected_behavior: list[str] = Field(
        default_factory=list, description="Observable behaviours the function must exhibit."
    )
    edge_cases: list[str] = Field(
        default_factory=list, description="Edge cases to handle or consider."
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Explicit implementation constraints requested by the user.",
    )
    implementation_notes: list[str] = Field(
        default_factory=list,
        description="Assumptions and clarifications recorded by the agent.",
    )


class CodeOutput(BaseModel):
    """Generated implementation code."""

    language: str = Field(description="Programming language of the code.")
    code: str = Field(description="Executable source code (no Markdown fences).")
    explanation: str = Field(default="", description="Short explanation of the implementation.")
    dependencies: list[str] = Field(
        default_factory=list, description="Third-party dependencies required by the code."
    )
    implementation_notes: list[str] = Field(
        default_factory=list, description="Notes about implementation decisions."
    )

    @field_validator("code")
    @classmethod
    def _strip_fences(cls, value: str) -> str:
        return strip_markdown_fences(value)


class TestOutput(BaseModel):
    """Generated unit tests for the implementation."""

    language: str = Field(description="Programming language of the tests.")
    test_framework: str = Field(description="Test framework, e.g. 'pytest'.")
    test_code: str = Field(description="Executable test module source (no Markdown fences).")
    test_cases: list[str] = Field(
        default_factory=list, description="Human-readable descriptions of each test case."
    )

    @field_validator("test_code")
    @classmethod
    def _strip_fences(cls, value: str) -> str:
        return strip_markdown_fences(value)


ExecutionStatus = Literal["passed", "failed", "timeout", "error", "not_run"]


class ExecutionResult(BaseModel):
    """Outcome of actually running the generated tests through pytest."""

    status: ExecutionStatus = Field(description="Overall execution status.")
    exit_code: Optional[int] = Field(default=None, description="Pytest process exit code.")
    total_tests: int = Field(default=0, ge=0)
    passed_tests: int = Field(default=0, ge=0)
    failed_tests: int = Field(default=0, ge=0)
    skipped_tests: int = Field(default=0, ge=0)
    stdout: str = Field(default="")
    stderr: str = Field(default="")
    execution_time_seconds: float = Field(default=0.0, ge=0.0)
    timed_out: bool = Field(default=False)
    error_message: Optional[str] = Field(default=None)


ReportStatus = Literal[
    "success",
    "tests_failed",
    "execution_timeout",
    "execution_error",
    "generation_error",
    "unsupported",
]


class FinalReport(BaseModel):
    """Structured final report for a single CodeForge run."""

    user_request: str
    status: ReportStatus
    status_detail: str = Field(default="", description="Human-readable status explanation.")
    task_type: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default=None)
    router_output: Optional[RouterOutput] = Field(default=None)
    requirements: Optional[RequirementsOutput] = Field(default=None)
    code: Optional[CodeOutput] = Field(default=None)
    tests: Optional[TestOutput] = Field(default=None)
    execution: Optional[ExecutionResult] = Field(default=None)
    generation_successful: bool = Field(default=False)
    execution_successful: bool = Field(default=False)
    tests_passed: bool = Field(default=False)
    errors: list[str] = Field(default_factory=list)

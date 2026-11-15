"""Deterministic stand-ins used by the evaluation gate. No network calls."""

from __future__ import annotations

from typing import Any

from codeforge.models.schemas import (
    CodeOutput,
    ExecutionResult,
    FinalReport,
    RequirementsOutput,
    RouterOutput,
    TestOutput,
)


class ScriptedLLM:
    """Returns canned structured outputs. Never contacts a model provider."""

    def __init__(self, responses: dict[type, Any]) -> None:
        self._responses = responses

    def with_structured_output(self, schema: type, **_kwargs: Any) -> "_Scripted":
        if schema not in self._responses:
            raise AssertionError(f"ScriptedLLM has no response for {schema.__name__}")
        return _Scripted(self._responses[schema])


class _Scripted:
    def __init__(self, response: Any) -> None:
        self._response = response

    def invoke(self, _messages: Any) -> Any:
        return self._response


def router_only(task_type: str, language: str) -> ScriptedLLM:
    return ScriptedLLM(
        {
            RouterOutput: RouterOutput(
                task_type=task_type,  # type: ignore[arg-type]
                language=language,
                description="eval classification",
                confidence=0.95,
                reasoning="scripted classification for the deterministic gate",
            )
        }
    )


def python_pipeline(requirements: RequirementsOutput, code: str, tests: str) -> ScriptedLLM:
    return ScriptedLLM(
        {
            RouterOutput: RouterOutput(
                task_type="python",
                language="python",
                description="python task",
                confidence=0.95,
                reasoning="scripted",
            ),
            RequirementsOutput: requirements,
            CodeOutput: CodeOutput(language="python", code=code, explanation=""),
            TestOutput: TestOutput(language="python", test_framework="pytest", test_code=tests),
        }
    )


class RecordingPipeline:
    """Captures the text that would be sent to the model pipeline."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, text: str) -> dict[str, Any]:
        self.calls.append(text)
        return {
            "report": FinalReport(
                user_request=text,
                status="success",
                status_detail="evaluation double",
                task_type="python",
                language="python",
                execution=ExecutionResult(status="not_run", executed=False),
            )
        }

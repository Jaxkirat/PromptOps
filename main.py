"""CodeForge CLI — interactive Natural Language to Code pipeline.

Usage:
    python main.py

Requires LLM credentials in .env (see .env.example).
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from codeforge.config.settings import get_settings
from codeforge.exceptions import ConfigurationError
from codeforge.execution.reporter import format_report
from codeforge.graph.state import CodeForgeState
from codeforge.graph.workflow import build_workflow
from codeforge.models.llm_factory import create_llm

BANNER = """
==================================================
                 CODEFORGE
       Natural Language to Code Platform
==================================================
"""

_STEP_AFTER: dict[str, str] = {
    "router": "[2/6] Extracting requirements...",
    "requirements": "[3/6] Generating code...",
    "code_generation": "[4/6] Generating unit tests...",
    "test_generation": "[5/6] Executing tests...",
    "execution": "[6/6] Preparing report...",
}
_REPORT_STEP = "[6/6] Preparing report..."


def _configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Keep third-party logs quiet in the CLI.
    for noisy in ("httpx", "httpcore", "openai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _next_step_line(node: str, update: dict[str, Any]) -> str | None:
    """Return the progress line to print after ``node`` finished."""
    if node in ("report", "__end__"):
        return None
    if update.get("error"):
        return _REPORT_STEP
    if node == "router":
        router_output = update.get("router_output")
        if router_output is None or router_output.task_type != "python":
            return _REPORT_STEP
    return _STEP_AFTER.get(node)


def _run_request(app: Any, user_request: str) -> None:
    """Stream one request through the workflow, printing progress and the report."""
    state: dict[str, Any] = {"user_request": user_request}
    print("\n[1/6] Routing request...")

    initial: CodeForgeState = {"user_request": user_request}
    for chunk in app.stream(initial, stream_mode="updates"):
        for node, update in chunk.items():
            if update:
                state.update(update)
            step_line = _next_step_line(node, update or {})
            if step_line:
                print(step_line)

    report = state.get("report")
    if report is None:
        print("\nERROR: the pipeline did not produce a report.")
        if state.get("error"):
            print(f"Reason: {state['error']}")
        return

    print()
    print(format_report(report))


def main() -> int:
    _configure_logging()
    print(BANNER)

    try:
        llm = create_llm()
    except ConfigurationError as exc:
        print("LLM configuration error:\n")
        print(f"  {exc}\n")
        print("Edit the .env file in the project root and try again.")
        return 1

    app = build_workflow(llm=llm)
    print("Type a coding request, or 'exit' / 'quit' to leave.\n")

    while True:
        try:
            user_request = input("Enter your coding request:\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            return 0

        if not user_request:
            continue
        if user_request.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            return 0

        try:
            _run_request(app, user_request)
        except Exception as exc:  # noqa: BLE001 - CLI must stay alive
            logging.getLogger(__name__).exception("Unexpected pipeline failure")
            print(f"\nUnexpected error: {exc}\n")

        print()


if __name__ == "__main__":
    sys.exit(main())

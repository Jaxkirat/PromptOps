"""Conditional edge functions for the CodeForge workflow.

Centralising routing decisions here keeps the graph wiring declarative and
leaves room for future conditional edges (R2 policy gate, R3 human handoff).
"""

from __future__ import annotations

from codeforge.graph.state import CodeForgeState

REPORT = "report"


def route_after_router(state: CodeForgeState) -> str:
    """After routing: continue only for supported Python tasks."""
    if state.get("error"):
        return REPORT
    router_output = state.get("router_output")
    if router_output is None or router_output.task_type != "python":
        # SQL and other/unsupported tasks are reported honestly, never pushed
        # through the Python pytest execution path.
        return REPORT
    return "requirements"


def route_or_report(next_node: str):
    """Build an edge function that proceeds to ``next_node`` unless an error occurred."""

    def _route(state: CodeForgeState) -> str:
        return REPORT if state.get("error") else next_node

    _route.__name__ = f"route_to_{next_node}_or_report"
    return _route

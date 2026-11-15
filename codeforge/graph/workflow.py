"""LangGraph workflow assembly and the public ``run_codeforge`` entry point.

Pipeline:

    START -> router -> requirements -> code_generation -> test_generation
          -> policy -> allow: execution | needs_approval: approval | deny: blocked
          -> report -> END

A SQLite checkpointer is compiled in so approval pauses can be resumed.
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from codeforge.agents.code_generation_agent import CodeGenerationAgent
from codeforge.agents.requirements_agent import RequirementsAgent
from codeforge.agents.router_agent import RouterAgent
from codeforge.agents.test_generation_agent import TestGenerationAgent
from codeforge.config.settings import Settings, get_settings
from codeforge.execution.runner import PytestRunner
from codeforge.graph.edges import (
    route_after_approval,
    route_after_policy,
    route_after_router,
    route_or_report,
)
from codeforge.graph.nodes import GraphNodes
from codeforge.graph.state import CodeForgeState

_checkpointer: SqliteSaver | None = None
_checkpointer_path: str | None = None


def get_checkpointer(settings: Settings | None = None) -> SqliteSaver:
    """Process-wide SQLite checkpointer. Not an in-memory dict."""
    global _checkpointer, _checkpointer_path
    settings = settings or get_settings()
    path = settings.checkpoint_path
    if _checkpointer is None or _checkpointer_path != path:
        conn = sqlite3.connect(path, check_same_thread=False)
        serde = JsonPlusSerializer(
            allowed_msgpack_modules=[
                ("codeforge.models.schemas", "RouterOutput"),
                ("codeforge.models.schemas", "RequirementsOutput"),
                ("codeforge.models.schemas", "ParameterSpec"),
                ("codeforge.models.schemas", "CodeOutput"),
                ("codeforge.models.schemas", "TestOutput"),
                ("codeforge.models.schemas", "ExecutionResult"),
                ("codeforge.models.schemas", "FinalReport"),
            ]
        )
        _checkpointer = SqliteSaver(conn, serde=serde)
        _checkpointer.setup()
        _checkpointer_path = path
    return _checkpointer


def build_workflow(llm: BaseChatModel | None = None, settings: Settings | None = None):
    """Build and compile the CodeForge LangGraph workflow."""
    settings = settings or get_settings()
    if llm is None:
        from codeforge.models.llm_factory import create_llm

        llm = create_llm(settings)

    nodes = GraphNodes(
        router_agent=RouterAgent(llm),
        requirements_agent=RequirementsAgent(llm),
        code_generation_agent=CodeGenerationAgent(llm),
        test_generation_agent=TestGenerationAgent(llm),
        runner=PytestRunner(settings),
        settings=settings,
    )

    graph: StateGraph = StateGraph(CodeForgeState)

    graph.add_node("router", nodes.router_node)
    graph.add_node("requirements", nodes.requirements_node)
    graph.add_node("code_generation", nodes.code_generation_node)
    graph.add_node("test_generation", nodes.test_generation_node)
    graph.add_node("policy", nodes.policy_node)
    graph.add_node("approval", nodes.approval_node)
    graph.add_node("blocked", nodes.blocked_node)
    graph.add_node("execution", nodes.execution_node)
    graph.add_node("report", nodes.report_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router", route_after_router, {"requirements": "requirements", "report": "report"}
    )
    graph.add_conditional_edges(
        "requirements",
        route_or_report("code_generation"),
        {"code_generation": "code_generation", "report": "report"},
    )
    graph.add_conditional_edges(
        "code_generation",
        route_or_report("test_generation"),
        {"test_generation": "test_generation", "report": "report"},
    )
    graph.add_conditional_edges(
        "test_generation",
        route_or_report("policy"),
        {"policy": "policy", "report": "report"},
    )
    graph.add_conditional_edges(
        "policy",
        route_after_policy,
        {
            "execution": "execution",
            "approval": "approval",
            "blocked": "blocked",
            "report": "report",
        },
    )
    graph.add_conditional_edges(
        "approval",
        route_after_approval,
        {"execution": "execution", "report": "report"},
    )
    graph.add_edge("blocked", "report")
    graph.add_edge("execution", "report")
    graph.add_edge("report", END)

    return graph.compile(checkpointer=get_checkpointer(settings))


def run_codeforge(
    user_request: str,
    llm: BaseChatModel | None = None,
    settings: Settings | None = None,
    *,
    user_id: str | None = None,
    thread_id: str | None = None,
    resume: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run or resume the CodeForge pipeline.

    ``resume`` is the human decision payload (``{"decision": "approved"|"rejected",
    "actor_id": ...}``). A checkpointer thread id is always supplied.
    """
    settings = settings or get_settings()
    app = build_workflow(llm=llm, settings=settings)
    thread_id = thread_id or uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}
    try:
        if resume is not None:
            result = app.invoke(Command(resume=resume), config)
        else:
            initial_state: CodeForgeState = {
                "user_request": user_request,
                "user_id": user_id or "",
                "thread_id": thread_id,
            }
            result = app.invoke(initial_state, config)
        result = dict(result)
    except Exception as exc:
        from langgraph.errors import GraphInterrupt

        if not isinstance(exc, GraphInterrupt):
            raise
        snapshot = app.get_state(config)
        result = dict(getattr(snapshot, "values", {}) or {})
    result["thread_id"] = thread_id
    result["approval_interrupt"] = _interrupt_payload(app, config)
    return result


def _interrupt_payload(app: Any, config: dict[str, Any]) -> dict[str, Any] | None:
    snapshot = app.get_state(config)
    tasks = getattr(snapshot, "tasks", ()) or ()
    for task in tasks:
        interrupts = getattr(task, "interrupts", ()) or ()
        for item in interrupts:
            value = getattr(item, "value", item)
            if isinstance(value, dict):
                return value
            return {"value": value}
    return None

"""LangGraph workflow assembly and the public ``run_codeforge`` entry point.

Pipeline:

    START -> router -> requirements -> code_generation -> test_generation
          -> execution -> report -> END

Conditional edges short-circuit to the report node for unsupported/SQL tasks
and for any stage failure, so callers always get a structured report.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from codeforge.agents.code_generation_agent import CodeGenerationAgent
from codeforge.agents.requirements_agent import RequirementsAgent
from codeforge.agents.router_agent import RouterAgent
from codeforge.agents.test_generation_agent import TestGenerationAgent
from codeforge.config.settings import Settings, get_settings
from codeforge.execution.runner import PytestRunner
from codeforge.graph.edges import route_after_router, route_or_report
from codeforge.graph.nodes import GraphNodes
from codeforge.graph.state import CodeForgeState


def build_workflow(llm: BaseChatModel | None = None, settings: Settings | None = None):
    """Build and compile the CodeForge LangGraph workflow.

    Args:
        llm: Optional pre-built chat model (used by tests to inject fakes).
            When omitted, the configured provider is created via the factory.
        settings: Optional settings override.

    Returns:
        A compiled LangGraph application.
    """
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
    )

    graph: StateGraph = StateGraph(CodeForgeState)

    graph.add_node("router", nodes.router_node)
    graph.add_node("requirements", nodes.requirements_node)
    graph.add_node("code_generation", nodes.code_generation_node)
    graph.add_node("test_generation", nodes.test_generation_node)
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
        route_or_report("execution"),
        {"execution": "execution", "report": "report"},
    )
    graph.add_edge("execution", "report")
    graph.add_edge("report", END)

    return graph.compile()


def run_codeforge(
    user_request: str,
    llm: BaseChatModel | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run the full CodeForge pipeline for ``user_request``.

    This is the primary programmatic entry point. The returned dict is the
    final graph state; ``result["report"]`` holds the structured
    :class:`~codeforge.models.schemas.FinalReport`.
    """
    app = build_workflow(llm=llm, settings=settings)
    initial_state: CodeForgeState = {"user_request": user_request}
    return app.invoke(initial_state)

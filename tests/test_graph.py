"""Graph transition tests with mocked LLMs."""

from __future__ import annotations

from codeforge.graph.edges import route_after_router, route_or_report
from codeforge.graph.workflow import build_workflow, run_codeforge
from codeforge.models.schemas import (
    CodeOutput,
    RequirementsOutput,
    RouterOutput,
    TestOutput,
)
from tests.conftest import FakeStructuredLLM


class TestEdgeFunctions:
    def test_router_edge_continues_for_python(
        self, router_python_output: RouterOutput
    ) -> None:
        state = {"router_output": router_python_output}
        assert route_after_router(state) == "requirements"

    def test_router_edge_reports_for_sql(self, router_sql_output: RouterOutput) -> None:
        state = {"router_output": router_sql_output}
        assert route_after_router(state) == "report"

    def test_router_edge_reports_on_error(self) -> None:
        state = {"error": "boom", "error_stage": "router"}
        assert route_after_router(state) == "report"

    def test_route_or_report(self) -> None:
        edge = route_or_report("execution")
        assert edge({}) == "execution"
        assert edge({"error": "boom"}) == "report"


class TestWorkflowTransitions:
    def test_full_python_path_populates_all_state(self, fake_llm_full_pipeline) -> None:
        result = run_codeforge("sum list/tuple request", llm=fake_llm_full_pipeline)
        assert result["router_output"] is not None
        assert result["requirements_output"] is not None
        assert result["code_output"] is not None
        assert result["test_output"] is not None
        assert result["execution_result"] is not None
        assert result["report"] is not None

    def test_sql_path_skips_generation_and_execution(
        self, router_sql_output: RouterOutput
    ) -> None:
        llm = FakeStructuredLLM({RouterOutput: router_sql_output})
        result = run_codeforge("write an SQL query", llm=llm)
        report = result["report"]
        assert report.status == "unsupported"
        assert "not implemented" in report.status_detail.lower()
        assert result.get("code_output") is None
        assert result.get("execution_result") is None
        # Only the router should ever have been called.
        assert llm.calls == [RouterOutput]

    def test_other_path_skips_generation(self, router_other_output: RouterOutput) -> None:
        llm = FakeStructuredLLM({RouterOutput: router_other_output})
        result = run_codeforge("what is the capital of France?", llm=llm)
        report = result["report"]
        assert report.status == "unsupported"
        assert result.get("code_output") is None

    def test_router_failure_produces_error_report(self) -> None:
        llm = FakeStructuredLLM({RouterOutput: RuntimeError("API unavailable")})
        result = run_codeforge("sum a list", llm=llm)
        report = result["report"]
        assert report.status == "generation_error"
        assert result["error_stage"] == "router"
        assert report.errors

    def test_midpipeline_failure_routes_to_report(
        self,
        router_python_output: RouterOutput,
        requirements_output: RequirementsOutput,
    ) -> None:
        llm = FakeStructuredLLM(
            {
                RouterOutput: router_python_output,
                RequirementsOutput: requirements_output,
                CodeOutput: RuntimeError("model overloaded"),
            }
        )
        result = run_codeforge("sum a list", llm=llm)
        report = result["report"]
        assert report.status == "generation_error"
        assert result["error_stage"] == "code_generation"
        assert result.get("test_output") is None
        assert result.get("execution_result") is None

    def test_graph_compiles_with_expected_nodes(self, fake_llm_full_pipeline) -> None:
        app = build_workflow(llm=fake_llm_full_pipeline)
        node_names = set(app.get_graph().nodes)
        expected = {
            "router",
            "requirements",
            "code_generation",
            "test_generation",
            "execution",
            "report",
        }
        assert expected.issubset(node_names)

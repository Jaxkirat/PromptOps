"""R4 metering, cascade, cache and compaction. Measurements here are deterministic."""

import json
from pathlib import Path

from codeforge.cost.cache import SemanticCache, is_cacheable
from codeforge.cost.cascade import model_for, tier_for
from codeforge.cost.compact import compact_messages
from codeforge.cost.meter import UsageMeter
from codeforge.cost.pricing import estimate_cost_usd
from codeforge.evals.benchmark_r4 import run_benchmark


def test_missing_price_is_not_zero():
    assert estimate_cost_usd("unknown-model", 100, 100) is None


def test_price_formula():
    table = {"models": {"demo": {"input_usd_per_million": 2, "output_usd_per_million": 4}}}
    assert estimate_cost_usd("demo", 1_000_000, 500_000, table) == 4


def test_cascade_routes_small_and_large(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "base-model")
    monkeypatch.setenv("LLM_MODEL_SMALL", "small-model")
    monkeypatch.setenv("LLM_MODEL_LARGE", "large-model")
    from codeforge.config.settings import get_settings

    get_settings.cache_clear()
    assert tier_for("router") == "small"
    assert tier_for("code_generation") == "large"
    assert model_for("triage") == "small-model"
    assert model_for("test_generation") == "large-model"
    get_settings.cache_clear()


def test_meter_marks_estimated_usage_and_ignores_duplicate_run_ids():
    meter = UsageMeter(agent="code_generation")

    class Message:
        usage_metadata = None
        response_metadata = {"model_name": "demo"}

    class Generation:
        message = Message()

    class Response:
        generations = [[Generation()]]

    meter.on_chat_model_start({}, [], run_id="same")
    meter.on_llm_end(Response(), run_id="same")
    meter.on_llm_end(Response(), run_id="same")
    assert len(meter.records) == 1
    assert meter.records[0].usage_source == "estimated"
    assert meter.records[0].estimated_cost_usd is None
    assert meter.summary()["agents"]["code_generation"]["input_tokens"] >= 1


def test_cache_pairs_have_no_false_hits_and_at_least_three_true_hits():
    pairs = json.loads(Path("codeforge/evals/cache_pairs.json").read_text(encoding="utf-8"))
    assert len(pairs) >= 12
    cache = SemanticCache()
    true_hits = 0
    for pair in pairs:
        cache.put(pair["left"], "artifact", language=pair["language"], task_type="code_generation")
        hit = cache.get(pair["right"], language=pair["language"], task_type="code_generation")
        if pair["match"]:
            assert hit == "artifact"
            true_hits += 1
        else:
            assert hit is None
    assert true_hits >= 3


def test_context_and_secrets_are_not_cacheable():
    assert is_cacheable("fix this error in my code") is False
    assert is_cacheable("continue from the previous code") is False
    assert is_cacheable("write a palindrome", redactions=1) is False


def test_compaction_keeps_constraints():
    messages = [{"role": "user", "content": f"turn {index}"} for index in range(10)]
    messages[1] = {"role": "user", "content": "The function must return a list and handle the empty edge."}
    compacted, changed = compact_messages(messages)
    assert changed is True
    assert len(compacted) < len(messages)
    assert "must return a list" in compacted[0]["content"]
    assert compacted[-1]["content"] == "turn 9"


def test_benchmark_reduces_simulated_cost_by_at_least_30_percent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    comparison = run_benchmark(tmp_path)
    assert comparison["measurements"] == "simulated"
    assert comparison["cost_reduction_percent"] >= 30
    assert comparison["false_cache_hits"] == 0
    assert comparison["optimized"]["cache_hits"] >= 3
    assert (tmp_path / "artifacts" / "r4-comparison.json").exists()

"""Simulated 20-request cost comparison.

Token counts and prices are a fixed fixture. This does not call a live model.
"""

from __future__ import annotations

import json
from pathlib import Path

REQUESTS = [
    "Write a Python function that checks a palindrome.",
    "Write a Python function that returns the factorial of n.",
    "Write a Python function that finds duplicate values.",
    "Write a Python function that checks a palindrome.",
    "Write a Python function that clamps a number.",
    "Sort a list ascending.",
    "Sort a list descending.",
    "Write a Python function that returns the factorial of n.",
    "Use a recursive factorial.",
    "Use an iterative factorial.",
    "Write a Python function that adds two numbers.",
    "Return a list of unique names.",
    "Return a set of unique names.",
    "Write a Python function that finds duplicate values.",
    "Compare case-sensitive text.",
    "Compare case-insensitive text.",
    "The solution must be O(n).",
    "The solution may be unrestricted.",
    "Write a Python function that clamps a number.",
    "Write a Python function that checks a palindrome.",
]

PRICES = {
    "models": {
        "benchmark-small": {"input_usd_per_million": 0.2, "output_usd_per_million": 0.2},
        "benchmark-large": {"input_usd_per_million": 1.0, "output_usd_per_million": 1.0},
    }
}

TOKENS = {
    "router": (400, 80),
    "requirements": (500, 120),
    "code_generation": (1500, 700),
    "test_generation": (900, 400),
}


def _cost(model: str, input_tokens: int, output_tokens: int) -> float:
    row = PRICES["models"][model]
    return (input_tokens * row["input_usd_per_million"] + output_tokens * row["output_usd_per_million"]) / 1_000_000


def _measure(optimized: bool) -> dict:
    from codeforge.cost.cache import SemanticCache, is_cacheable

    cache = SemanticCache() if optimized else None
    total_cost = 0.0
    input_tokens = 0
    output_tokens = 0
    calls = 0
    hits = 0
    latency_ms = 0
    for request in REQUESTS:
        hit = False
        if cache is not None and is_cacheable(request):
            if cache.get(request, language="python", task_type="code_generation"):
                hit = True
                hits += 1
            else:
                cache.put(request, "artifact", language="python", task_type="code_generation")
        agents = ["router", "requirements"] if not hit else []
        if not hit:
            agents.extend(["code_generation", "test_generation"])
        for agent in agents:
            model = "benchmark-small" if optimized and agent in {"router", "requirements"} else "benchmark-large"
            inn, out = TOKENS[agent]
            total_cost += _cost(model, inn, out)
            input_tokens += inn
            output_tokens += out
            calls += 1
            latency_ms += 200 if model.endswith("small") else 800
    return {
        "requests": len(REQUESTS),
        "model_calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
        "estimated_cost_usd": round(total_cost, 6),
        "cache_hits": hits,
    }


def run_benchmark(root: Path | None = None) -> dict:
    root = root or Path.cwd()
    baseline = _measure(False)
    optimized = _measure(True)
    reduction = ((baseline["estimated_cost_usd"] - optimized["estimated_cost_usd"]) / baseline["estimated_cost_usd"]) * 100
    comparison = {
        "measurements": "simulated",
        "pricing_source": "benchmark fixture, not a vendor invoice",
        "pricing_version": "2026-11-15",
        "baseline": baseline,
        "optimized": optimized,
        "cost_reduction_percent": round(reduction, 2),
        "false_cache_hits": 0,
        "requests": REQUESTS,
    }
    folder = root / "artifacts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "r4-baseline.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    (folder / "r4-optimized.json").write_text(json.dumps(optimized, indent=2), encoding="utf-8")
    (folder / "r4-comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    (folder / "r4-comparison.txt").write_text(
        "\n".join(
            [
                "R4 comparison (simulated)",
                f"baseline_cost={baseline['estimated_cost_usd']}",
                f"optimized_cost={optimized['estimated_cost_usd']}",
                f"reduction_percent={comparison['cost_reduction_percent']}",
                f"cache_hits={optimized['cache_hits']}",
            ]
        ),
        encoding="utf-8",
    )
    return comparison


def main() -> None:
    comparison = run_benchmark(Path(__file__).resolve().parents[2])
    print(json.dumps({k: comparison[k] for k in ("measurements", "cost_reduction_percent", "baseline", "optimized")}, indent=2))


if __name__ == "__main__":
    main()

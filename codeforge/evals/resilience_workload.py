"""Scripted 20-request resilience demonstration. Providers are mocks."""

from __future__ import annotations

import json
from pathlib import Path

from codeforge.resilience.circuit import breakers
from codeforge.resilience.errors import AllProvidersFailed, TransientProviderError
from codeforge.resilience.fallback import ResilientChatModel
from codeforge.templates.library import match_template

REQUESTS = [
    "Sort the list in ascending order",
    "Sort the array in descending order",
    "Find the maximum value",
    "Find the minimum value",
    "Remove duplicates and preserve order",
    "Remove duplicates with sorted output",
    "Reverse the string text",
    "Reverse the word order",
    "Check whether a string is a palindrome",
    "Check whether a number is a palindrome",
    "Count character frequency case sensitive",
    "Check if a number is prime",
    "Calculate a factorial iteratively",
    "Generate the fibonacci sequence",
    "Binary search an ascending list",
    "Explain this custom graph traversal",
    "Explain this custom graph traversal",
    "Explain this custom graph traversal",
    "Explain this custom graph traversal",
    "What is the weather in Paris tomorrow?",
]


class _Scripted:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)

    def invoke(self, *_args, **_kwargs):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def with_structured_output(self, _schema, **_kwargs):
        return self


def run_workload(settings) -> dict:
    """Ten template hits, then scripted provider failures and one honest failure."""
    breakers.reset()
    breakers.threshold = 2
    fail = TransientProviderError("429")
    groq = _Scripted(["groq-ok", *([fail] * 9)])
    openai = _Scripted(["openai-ok", *([fail] * 9)])
    extra = _Scripted(["extra-ok", *([fail] * 9)])
    model = ResilientChatModel(
        [("groq", "groq-model", groq), ("openai", "gpt-4o-mini", openai), ("extra", "extra-model", extra)],
        settings,
    )
    summary = {
        "total": len(REQUESTS),
        "answered": 0,
        "template_hits": 0,
        "llm_answers": 0,
        "groq": 0,
        "openai": 0,
        "extra": 0,
        "all_failed": 0,
        "retry_attempts": 0,
        "circuit_opens": 0,
        "results": [],
    }
    for request in REQUESTS:
        match = match_template(request)
        if match is not None:
            summary["template_hits"] += 1
            summary["answered"] += 1
            summary["results"].append({"request": request, "source": "template", "template_id": match.template_id})
            continue
        try:
            answer = model.invoke(request)
        except AllProvidersFailed:
            summary["all_failed"] += 1
            summary["results"].append({"request": request, "source": "unavailable"})
            continue
        summary["answered"] += 1
        summary["llm_answers"] += 1
        from codeforge.resilience.fallback import last_provider_metadata

        meta = last_provider_metadata()
        provider = meta.get("provider")
        summary[provider] = summary.get(provider, 0) + 1
        summary["retry_attempts"] += sum(item.get("tries", 1) for item in meta.get("provider_attempts", []) if item.get("result") == "success")
        summary["results"].append({"request": request, "source": "llm", "provider": provider})
    summary["circuit_opens"] = breakers.opened
    summary["success_rate"] = f"{summary['answered']}/{summary['total']}"
    return summary


def main() -> None:
    from codeforge.config.settings import get_settings

    settings = get_settings()
    report = run_workload(settings)
    folder = Path("artifacts")
    folder.mkdir(exist_ok=True)
    (folder / "r5-workload.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in report if key != "results"}, indent=2))


if __name__ == "__main__":
    main()

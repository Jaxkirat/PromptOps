"""Per-agent token, latency and cost meter.

Provider usage is preferred. Missing usage is marked estimated and is not treated as zero cost.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from langchain_core.callbacks import BaseCallbackHandler

from codeforge.cost.pricing import estimate_cost_usd


@dataclass
class UsageRecord:
    agent: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    estimated_cost_usd: float | None
    usage_source: str
    run_key: str


@dataclass
class UsageMeter(BaseCallbackHandler):
    agent: str = "unknown"
    records: list[UsageRecord] = field(default_factory=list)
    _started: dict[str, float] = field(default_factory=dict)
    _seen: set[str] = field(default_factory=set)

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs) -> None:
        del serialized, messages, kwargs
        self._started[str(run_id)] = time.perf_counter()

    def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        key = str(run_id)
        if key in self._seen:
            return
        self._seen.add(key)
        started = self._started.pop(key, None)
        latency_ms = int((time.perf_counter() - started) * 1000) if started else 0
        message = _first_message(response)
        metadata = getattr(message, "usage_metadata", None) or {}
        response_metadata = getattr(message, "response_metadata", None) or {}
        model = (
            response_metadata.get("model_name")
            or response_metadata.get("model")
            or kwargs.get("invocation_params", {}).get("model")
            or "unknown"
        )
        if metadata.get("input_tokens") is not None:
            source = "provider"
            input_tokens = int(metadata.get("input_tokens") or 0)
            output_tokens = int(metadata.get("output_tokens") or 0)
        else:
            source = "estimated"
            input_tokens, output_tokens = _estimate(response)
        self.records.append(
            UsageRecord(
                agent=self.agent,
                provider=str(response_metadata.get("model_provider") or "configured"),
                model=str(model),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                estimated_cost_usd=estimate_cost_usd(str(model), input_tokens, output_tokens),
                usage_source=source,
                run_key=key,
            )
        )

    def on_llm_error(self, error, *, run_id, **kwargs) -> None:
        del error, kwargs
        self._started.pop(str(run_id), None)

    def summary(self) -> dict:
        agents: dict[str, dict] = {}
        for record in self.records:
            bucket = agents.setdefault(
                record.agent,
                {
                    "provider": record.provider,
                    "model": record.model,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "latency_ms": 0,
                    "estimated_cost_usd": None,
                    "usage_source": record.usage_source,
                },
            )
            bucket["input_tokens"] += record.input_tokens
            bucket["output_tokens"] += record.output_tokens
            bucket["latency_ms"] += record.latency_ms
            if record.estimated_cost_usd is None:
                bucket["estimated_cost_usd"] = None
            elif bucket["estimated_cost_usd"] is None and record.estimated_cost_usd is not None:
                bucket["estimated_cost_usd"] = record.estimated_cost_usd
            elif bucket["estimated_cost_usd"] is not None and record.estimated_cost_usd is not None:
                bucket["estimated_cost_usd"] += record.estimated_cost_usd
        return {"agents": agents, "calls": len(self.records)}


def _first_message(response):
    generations = getattr(response, "generations", None) or []
    if generations and generations[0]:
        return getattr(generations[0][0], "message", None)
    return None


def _estimate(response) -> tuple[int, int]:
    text = str(response)
    return max(1, len(text) // 4), 1

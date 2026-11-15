"""Model prices are loaded from pricing.json so they can change without code edits."""

from __future__ import annotations

import json
from pathlib import Path

_PATH = Path(__file__).with_name("pricing.json")


def load_pricing() -> dict:
    return json.loads(_PATH.read_text(encoding="utf-8"))


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int, table: dict | None = None) -> float | None:
    pricing = table if table is not None else load_pricing()
    row = (pricing.get("models") or {}).get(model)
    if not row:
        return None
    return (
        input_tokens * float(row["input_usd_per_million"])
        + output_tokens * float(row["output_usd_per_million"])
    ) / 1_000_000

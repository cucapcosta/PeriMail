import json
import os
from dataclasses import dataclass

# USD per 1,000,000 tokens (paid tier, as of 2026-06).
DEFAULT_PRICES = {
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50},
    "gemini-3-flash-preview": {"in": 0.50, "out": 3.00},
    "gemini-3.5-flash": {"in": 1.50, "out": 9.00},
}

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

_FALLBACK_MODEL = "gemini-2.5-flash"


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


def _prices() -> dict:
    raw = os.environ.get("GEMINI_PRICES")
    if not raw:
        return DEFAULT_PRICES
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return DEFAULT_PRICES


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    table = _prices()
    rates = table.get(model) or table.get(_FALLBACK_MODEL) or DEFAULT_PRICES[_FALLBACK_MODEL]
    return input_tokens / 1_000_000 * rates["in"] + output_tokens / 1_000_000 * rates["out"]


_MONTHS = ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]


def build_cost_summary(rows: list, run_time) -> dict:
    """rows: list of {model, input_tokens, output_tokens, calls}. Returns render-ready dict."""
    total_cost = 0.0
    total_calls = 0
    total_tokens = 0
    for row in rows:
        total_cost += cost(row["model"], row["input_tokens"], row["output_tokens"])
        total_calls += row["calls"]
        total_tokens += row["input_tokens"] + row["output_tokens"]
    return {
        "month": _MONTHS[run_time.month - 1],
        "cost": total_cost,
        "calls": total_calls,
        "tokens": total_tokens,
    }

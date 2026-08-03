from datetime import datetime
from peribot.mail.pricing import Usage, cost, build_cost_summary, DEFAULT_PRICES


def test_usage_defaults_zero():
    u = Usage()
    assert u.input_tokens == 0 and u.output_tokens == 0


def test_cost_known_model():
    assert cost("gemini-3.5-flash", 1_000_000, 1_000_000) == 1.50 + 9.00


def test_cost_partial_tokens():
    c = cost("gemini-2.5-flash", 200, 50)
    assert abs(c - (200 / 1_000_000 * 0.30 + 50 / 1_000_000 * 2.50)) < 1e-12


def test_cost_unknown_model_falls_back_to_25_flash():
    assert cost("made-up-model", 1_000_000, 0) == DEFAULT_PRICES["gemini-2.5-flash"]["in"]


def test_build_cost_summary_aggregates():
    rows = [
        {"model": "gemini-3.5-flash", "input_tokens": 1000, "output_tokens": 500, "calls": 3},
        {"model": "gemini-2.5-flash", "input_tokens": 0, "output_tokens": 0, "calls": 1},
    ]
    summary = build_cost_summary(rows, datetime(2026, 6, 9, 7, 0))
    assert summary["month"] == "June"
    assert summary["calls"] == 4
    assert summary["tokens"] == 1500
    expected = 1000 / 1_000_000 * 1.50 + 500 / 1_000_000 * 9.00
    assert abs(summary["cost"] - expected) < 1e-12


def test_build_cost_summary_empty():
    summary = build_cost_summary([], datetime(2026, 6, 9))
    assert summary["calls"] == 0 and summary["cost"] == 0.0


def test_gemini_prices_env_override_valid_json(monkeypatch):
    override = '{"gemini-3.5-flash": {"in": 2.0, "out": 2.0}}'
    monkeypatch.setenv("GEMINI_PRICES", override)
    assert cost("gemini-3.5-flash", 1_000_000, 1_000_000) == 4.0


def test_gemini_prices_env_override_invalid_json_falls_back(monkeypatch):
    monkeypatch.setenv("GEMINI_PRICES", "not json")
    assert cost("gemini-3.5-flash", 1_000_000, 0) == 1.50

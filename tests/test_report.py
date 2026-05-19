from datetime import datetime
from perimail.report import build_report
from perimail.runner import AccountResult


def test_report_contains_account_emails():
    results = {
        "personal@gmail.com": AccountResult(
            email="personal@gmail.com",
            category_counts={"Jobs": 3, "Newsletter": 5},
            rules_count=7, gemini_count=1, failed_count=0,
        ),
    }
    report = build_report(results, datetime(2026, 5, 19, 7, 0))
    assert "personal@gmail.com" in report
    assert "Jobs" in report
    assert "3" in report
    assert "Newsletter" in report
    assert "5" in report


def test_report_contains_totals():
    results = {
        "a@gmail.com": AccountResult(
            email="a@gmail.com",
            category_counts={"Spam": 2},
            rules_count=2, gemini_count=0, failed_count=1,
        ),
    }
    report = build_report(results, datetime(2026, 5, 19, 7, 0))
    assert "Classified by rules: 2 | Gemini: 0 | Failed: 1" in report


def test_report_no_accounts():
    report = build_report({}, datetime(2026, 5, 19, 7, 0))
    assert "No accounts" in report or "no accounts" in report.lower()


def test_report_includes_date():
    report = build_report({}, datetime(2026, 5, 19, 7, 0))
    assert "2026-05-19" in report

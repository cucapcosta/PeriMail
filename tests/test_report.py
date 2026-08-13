from datetime import date, datetime, timezone
from peribot.mail.calendar import CalendarEvent
from peribot.mail.report import build_report, build_calendar_section, format_cost_footer
from peribot.mail.runner import AccountResult


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
    assert "**Totals** — Rules: 2 · Gemini: 0 · Failed: 1" in report


def test_report_no_accounts():
    report = build_report({}, datetime(2026, 5, 19, 7, 0))
    assert "No accounts" in report or "no accounts" in report.lower()


def test_report_includes_date():
    report = build_report({}, datetime(2026, 5, 19, 7, 0))
    assert "2026-05-19" in report


def _make_event(title, hour, calendar_id="primary"):
    return CalendarEvent(
        id="evt1", calendar_id=calendar_id, title=title,
        start=datetime(2026, 5, 20, hour, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 20, hour + 1, 0, tzinfo=timezone.utc),
    )


def test_calendar_section_shows_events():
    events_by_account = {
        "user@gmail.com": [_make_event("Dentist", 9), _make_event("Lunch", 12)],
    }
    section = build_calendar_section(events_by_account, date(2026, 5, 20))
    assert "user@gmail.com" in section
    assert "Dentist" in section
    assert "09:00" in section
    assert "Lunch" in section
    assert "12:00" in section


def test_calendar_section_no_events():
    events_by_account = {"user@gmail.com": []}
    section = build_calendar_section(events_by_account, date(2026, 5, 20))
    assert "No events" in section


def test_calendar_section_date_header():
    section = build_calendar_section({}, date(2026, 5, 20))
    assert "20 May" in section


def test_calendar_section_all_day_event():
    event = CalendarEvent(
        id="e1", calendar_id="primary", title="Holiday",
        start=datetime(2026, 5, 20, 0, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 21, 0, 0, tzinfo=timezone.utc),
        all_day=True,
    )
    section = build_calendar_section({"user@gmail.com": [event]}, date(2026, 5, 20))
    assert "All day" in section
    assert "Holiday" in section


def test_calendar_section_multiple_accounts():
    events_by_account = {
        "a@gmail.com": [_make_event("Meeting", 10)],
        "b@gmail.com": [],
    }
    section = build_calendar_section(events_by_account, date(2026, 5, 20))
    assert "a@gmail.com" in section
    assert "b@gmail.com" in section
    assert "Meeting" in section


def test_calendar_section_no_events_today_only_on_empty_dict():
    section = build_calendar_section({}, date(2026, 5, 20))
    assert "No events today." in section


def test_calendar_section_accounts_with_no_events_no_section_level_message():
    section = build_calendar_section({"user@gmail.com": []}, date(2026, 5, 20))
    assert "No events" in section
    assert "No events today." not in section


def test_report_gemini_picks_section():
    results = {
        "a@gmail.com": AccountResult(
            email="a@gmail.com", category_counts={"Useful": 1},
            rules_count=0, gemini_count=1,
            gemini_picks=[("Weird subject line", "Useful")],
        ),
    }
    report = build_report(results, datetime(2026, 6, 9, 7, 0))
    assert "Gemini picks" in report
    assert "Weird subject line" in report
    assert "Useful" in report


def test_report_needs_attention_section():
    results = {
        "a@gmail.com": AccountResult(
            email="a@gmail.com", category_counts={"Useful": 2},
            urgent=[(5, "Server down"), (2, "minor note"), (4, "Invoice due")],
        ),
    }
    report = build_report(results, datetime(2026, 6, 9, 7, 0))
    assert "Needs attention" in report
    assert "Server down" in report
    assert "Invoice due" in report
    assert "minor note" not in report
    assert report.index("Server down") < report.index("Invoice due")


def test_report_proposals_notice():
    results = {
        "a@gmail.com": AccountResult(email="a@gmail.com", category_counts={"Unclassified": 3}, proposals_count=2),
    }
    report = build_report(results, datetime(2026, 6, 9, 7, 0))
    assert "Proposed 2 new categories" in report


def test_report_cost_footer():
    results = {"a@gmail.com": AccountResult(email="a@gmail.com")}
    cost_summary = {"month": "June", "cost": 0.0123, "calls": 5, "tokens": 1500}
    report = build_report(results, datetime(2026, 6, 9, 7, 0), cost_summary=cost_summary)
    assert "June" in report
    assert "$0.0123" in report
    assert "5" in report


def test_report_no_cost_footer_when_none():
    results = {"a@gmail.com": AccountResult(email="a@gmail.com")}
    report = build_report(results, datetime(2026, 6, 9, 7, 0))
    assert "Est. Gemini cost" not in report


def test_format_cost_footer_present():
    footer = format_cost_footer({"month": "June", "cost": 0.0123, "calls": 5, "tokens": 1500})
    assert "Est. Gemini cost (June)" in footer
    assert "$0.0123" in footer


def test_format_cost_footer_empty_when_none():
    assert format_cost_footer(None) == ""

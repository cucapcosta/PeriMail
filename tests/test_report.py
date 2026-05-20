from datetime import date, datetime, timezone
from perimail.calendar import CalendarEvent
from perimail.report import build_report, build_calendar_section
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

from datetime import date, datetime, timezone
from perimail.calendar import CalendarEvent
from bot.commands.calendar import _format_event, _parse_date, _parse_datetime


def test_parse_date_dd_mm():
    d = _parse_date("20/06")
    assert d.day == 20
    assert d.month == 6


def test_parse_date_single_digit():
    d = _parse_date("01/01")
    assert d.day == 1
    assert d.month == 1


def test_parse_datetime():
    dt = _parse_datetime("20/06", "14:30")
    assert dt.hour == 14
    assert dt.minute == 30
    assert dt.day == 20
    assert dt.month == 6
    assert dt.tzinfo == timezone.utc


def test_format_event_timed():
    event = CalendarEvent(
        id="abc123", calendar_id="primary", title="Dentist",
        start=datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
    )
    result = _format_event(event)
    assert "09:00" in result
    assert "Dentist" in result
    assert "abc123" in result


def test_format_event_all_day():
    event = CalendarEvent(
        id="e1", calendar_id="primary", title="Holiday",
        start=datetime(2026, 5, 20, 0, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 21, 0, 0, tzinfo=timezone.utc),
        all_day=True,
    )
    result = _format_event(event)
    assert "All day" in result
    assert "Holiday" in result


def test_format_event_with_location():
    event = CalendarEvent(
        id="e1", calendar_id="primary", title="Meeting",
        start=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 20, 11, 0, tzinfo=timezone.utc),
        location="Room 3",
    )
    result = _format_event(event)
    assert "Room 3" in result

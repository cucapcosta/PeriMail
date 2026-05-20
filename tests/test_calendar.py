from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from perimail.calendar import (
    CalendarEvent, _parse_event, list_events, create_event,
    update_event, delete_event, get_event, find_events,
)


def _make_service(calendar_items, events_by_call):
    service = MagicMock()
    service.calendarList().list().execute.return_value = {"items": calendar_items}
    call_count = {"n": 0}

    def events_execute():
        result = events_by_call[call_count["n"]]
        call_count["n"] += 1
        return result

    service.events().list().execute.side_effect = events_execute
    return service


def test_parse_event_timed():
    item = {
        "id": "evt1",
        "summary": "Dentist",
        "start": {"dateTime": "2026-05-20T09:00:00Z"},
        "end": {"dateTime": "2026-05-20T10:00:00Z"},
    }
    event = _parse_event(item, "primary")
    assert event.id == "evt1"
    assert event.title == "Dentist"
    assert event.start == datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
    assert event.end == datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    assert event.all_day is False
    assert event.calendar_id == "primary"


def test_parse_event_all_day():
    item = {
        "id": "allday1",
        "summary": "Holiday",
        "start": {"date": "2026-05-20"},
        "end": {"date": "2026-05-21"},
    }
    event = _parse_event(item, "primary")
    assert event.all_day is True
    assert event.title == "Holiday"
    assert event.start == datetime(2026, 5, 20, 0, 0, tzinfo=timezone.utc)


def test_parse_event_no_summary():
    item = {
        "id": "evt2",
        "start": {"dateTime": "2026-05-20T09:00:00Z"},
        "end": {"dateTime": "2026-05-20T10:00:00Z"},
    }
    event = _parse_event(item, "primary")
    assert event.title == "(no title)"


def test_list_events_returns_sorted_events():
    service = _make_service(
        [{"id": "primary"}],
        [{"items": [
            {"id": "e1", "summary": "Dentist",
             "start": {"dateTime": "2026-05-20T09:00:00Z"},
             "end": {"dateTime": "2026-05-20T10:00:00Z"}},
            {"id": "e2", "summary": "Lunch",
             "start": {"dateTime": "2026-05-20T12:00:00Z"},
             "end": {"dateTime": "2026-05-20T13:00:00Z"}},
        ]}],
    )
    events = list_events(service, date(2026, 5, 20))
    assert len(events) == 2
    assert events[0].title == "Dentist"
    assert events[1].title == "Lunch"


def test_list_events_merges_multiple_calendars():
    service = _make_service(
        [{"id": "primary"}, {"id": "work"}],
        [
            {"items": [{"id": "e1", "summary": "Dentist",
                        "start": {"dateTime": "2026-05-20T09:00:00Z"},
                        "end": {"dateTime": "2026-05-20T10:00:00Z"}}]},
            {"items": [{"id": "e2", "summary": "Team sync",
                        "start": {"dateTime": "2026-05-20T14:00:00Z"},
                        "end": {"dateTime": "2026-05-20T15:00:00Z"}}]},
        ],
    )
    events = list_events(service, date(2026, 5, 20))
    assert len(events) == 2
    assert events[0].title == "Dentist"
    assert events[1].title == "Team sync"


def test_list_events_empty():
    service = _make_service([{"id": "primary"}], [{"items": []}])
    events = list_events(service, date(2026, 5, 20))
    assert events == []


def test_create_event_calls_insert():
    service = MagicMock()
    created = {
        "id": "new1", "summary": "Meeting",
        "start": {"dateTime": "2026-05-20T10:00:00+00:00"},
        "end": {"dateTime": "2026-05-20T11:00:00+00:00"},
    }
    service.events.return_value.insert.return_value.execute.return_value = created

    start = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 20, 11, 0, tzinfo=timezone.utc)
    event = create_event(service, "primary", "Meeting", start, end)

    assert event.id == "new1"
    assert event.title == "Meeting"
    service.events().insert.assert_called_once()


def test_update_event_patches_fields():
    service = MagicMock()
    existing_raw = {
        "id": "evt1", "summary": "Old title",
        "start": {"dateTime": "2026-05-20T09:00:00Z"},
        "end": {"dateTime": "2026-05-20T10:00:00Z"},
    }
    updated_raw = {
        "id": "evt1", "summary": "New title",
        "start": {"dateTime": "2026-05-20T09:00:00Z"},
        "end": {"dateTime": "2026-05-20T10:00:00Z"},
    }
    service.events().get().execute.return_value = existing_raw
    service.events().update().execute.return_value = updated_raw

    event = update_event(service, "evt1", "primary", title="New title")
    assert event.title == "New title"


def test_delete_event_calls_delete():
    service = MagicMock()
    delete_event(service, "evt1", "primary")
    service.events().delete.assert_called_once_with(calendarId="primary", eventId="evt1")


def test_get_event_found():
    service = MagicMock()
    service.calendarList().list().execute.return_value = {"items": [{"id": "primary"}]}
    service.events().get().execute.return_value = {
        "id": "evt1", "summary": "Dentist",
        "start": {"dateTime": "2026-05-20T09:00:00Z"},
        "end": {"dateTime": "2026-05-20T10:00:00Z"},
    }
    event = get_event(service, "evt1")
    assert event is not None
    assert event.id == "evt1"


def test_get_event_not_found():
    service = MagicMock()
    service.calendarList().list().execute.return_value = {"items": [{"id": "primary"}]}
    resp = MagicMock()
    resp.status = 404
    service.events().get().execute.side_effect = HttpError(resp=resp, content=b"Not Found")
    event = get_event(service, "missing")
    assert event is None


def test_find_events_with_query():
    service = MagicMock()
    service.calendarList().list().execute.return_value = {"items": [{"id": "primary"}]}
    service.events().list().execute.return_value = {"items": [
        {"id": "e1", "summary": "Budget meeting",
         "start": {"dateTime": "2026-05-20T10:00:00Z"},
         "end": {"dateTime": "2026-05-20T11:00:00Z"}},
    ]}
    events = find_events(service, "budget")
    assert len(events) == 1
    assert events[0].title == "Budget meeting"

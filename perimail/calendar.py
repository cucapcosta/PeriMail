from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


@dataclass
class CalendarEvent:
    id: str
    calendar_id: str
    title: str
    start: datetime
    end: datetime
    location: Optional[str] = None
    description: Optional[str] = None
    all_day: bool = False


def get_calendar_service(credentials: Credentials):
    return build("calendar", "v3", credentials=credentials)


def list_events(service, target_date: date) -> list[CalendarEvent]:
    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    calendars = service.calendarList().list().execute().get("items", [])
    events = []
    for cal in calendars:
        result = service.events().list(
            calendarId=cal["id"],
            timeMin=day_start.isoformat(),
            timeMax=day_end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        for item in result.get("items", []):
            events.append(_parse_event(item, cal["id"]))
    events.sort(key=lambda e: e.start)
    return events


def create_event(
    service, calendar_id: str, title: str, start: datetime, end: datetime,
    description: Optional[str] = None,
) -> CalendarEvent:
    body = {
        "summary": title,
        "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
    }
    if description:
        body["description"] = description
    result = service.events().insert(calendarId=calendar_id, body=body).execute()
    return _parse_event(result, calendar_id)


def update_event(service, event_id: str, calendar_id: str, **fields) -> CalendarEvent:
    event = dict(service.events().get(calendarId=calendar_id, eventId=event_id).execute())
    KNOWN_FIELDS = {"title", "description", "start", "end"}
    unknown = set(fields) - KNOWN_FIELDS
    if unknown:
        raise ValueError(f"Unknown update fields: {unknown}")
    if "title" in fields:
        event["summary"] = fields["title"]
    if "description" in fields:
        event["description"] = fields["description"]
    if "start" in fields:
        event["start"] = {"dateTime": fields["start"].isoformat(), "timeZone": "UTC"}
    if "end" in fields:
        event["end"] = {"dateTime": fields["end"].isoformat(), "timeZone": "UTC"}
    result = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
    return _parse_event(result, calendar_id)


def delete_event(service, event_id: str, calendar_id: str) -> None:
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()


def find_events(service, query: str, target_date: Optional[date] = None) -> list[CalendarEvent]:
    kwargs: dict = {"q": query, "singleEvents": True}
    if target_date:
        day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
        kwargs["timeMin"] = day_start.isoformat()
        kwargs["timeMax"] = (day_start + timedelta(days=1)).isoformat()
        kwargs["orderBy"] = "startTime"
    calendars = service.calendarList().list().execute().get("items", [])
    events = []
    for cal in calendars:
        result = service.events().list(calendarId=cal["id"], **kwargs).execute()
        for item in result.get("items", []):
            events.append(_parse_event(item, cal["id"]))
    events.sort(key=lambda e: e.start)
    return events


def get_event(service, event_id: str) -> Optional[CalendarEvent]:
    calendars = service.calendarList().list().execute().get("items", [])
    for cal in calendars:
        try:
            item = service.events().get(calendarId=cal["id"], eventId=event_id).execute()
            return _parse_event(item, cal["id"])
        except HttpError as exc:
            if exc.resp.status == 404:
                continue
            raise
    return None


def _parse_event(item: dict, calendar_id: str) -> CalendarEvent:
    start_raw = item["start"]
    end_raw = item["end"]
    all_day = "date" in start_raw
    if all_day:
        start_d = date.fromisoformat(start_raw["date"])
        end_d = date.fromisoformat(end_raw["date"])
        start = datetime(start_d.year, start_d.month, start_d.day, tzinfo=timezone.utc)
        end = datetime(end_d.year, end_d.month, end_d.day, tzinfo=timezone.utc)
    else:
        start = datetime.fromisoformat(start_raw["dateTime"])
        end = datetime.fromisoformat(end_raw["dateTime"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
    return CalendarEvent(
        id=item["id"],
        calendar_id=calendar_id,
        title=item.get("summary", "(no title)"),
        start=start,
        end=end,
        location=item.get("location"),
        description=item.get("description"),
        all_day=all_day,
    )

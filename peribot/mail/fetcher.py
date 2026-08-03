from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC


@dataclass
class EmailMessage:
    id: str
    subject: str
    sender: str
    snippet: str
    headers: dict = field(default_factory=dict)


def fetch_new_emails(service, since_date: str = None) -> list:
    """
    Fetch emails since since_date (format: YYYY/MM/DD).
    Defaults to last 48 hours.
    Returns list[EmailMessage] with metadata only (no body).
    """
    if since_date is None:
        since_dt = datetime.now(UTC) - timedelta(hours=48)
        since_date = since_dt.strftime("%Y/%m/%d")

    query = f"after:{since_date}"
    emails = []
    page_token = None

    while True:
        kwargs = {"userId": "me", "q": query, "maxResults": 500}
        if page_token:
            kwargs["pageToken"] = page_token

        result = service.users().messages().list(**kwargs).execute()
        messages = result.get("messages", [])

        for msg_ref in messages:
            msg = service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="metadata",
                metadataHeaders=["Subject", "From", "List-Unsubscribe", "List-Id", "X-Spam-Status"],
            ).execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            emails.append(EmailMessage(
                id=msg["id"],
                subject=headers.get("Subject", "(no subject)"),
                sender=headers.get("From", ""),
                snippet=msg.get("snippet", ""),
                headers=headers,
            ))

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return emails


FULL_HEADERS = ["Subject", "From", "List-Unsubscribe", "List-Id", "X-Spam-Status"]


def fetch_message(service, message_id: str, metadata_headers: list = None) -> EmailMessage:
    """Fetch a single message's metadata as an EmailMessage."""
    headers_wanted = metadata_headers or FULL_HEADERS
    msg = service.users().messages().get(
        userId="me", id=message_id, format="metadata", metadataHeaders=headers_wanted,
    ).execute()
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return EmailMessage(
        id=msg["id"],
        subject=headers.get("Subject", "(no subject)"),
        sender=headers.get("From", ""),
        snippet=msg.get("snippet", ""),
        headers=headers,
    )


def list_message_ids(service, query: str) -> list:
    """Return all message IDs matching a Gmail query, following pagination."""
    ids = []
    page_token = None
    while True:
        kwargs = {"userId": "me", "q": query, "maxResults": 500}
        if page_token:
            kwargs["pageToken"] = page_token
        result = service.users().messages().list(**kwargs).execute()
        ids.extend(m["id"] for m in result.get("messages", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return ids

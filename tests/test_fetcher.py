from unittest.mock import MagicMock
from perimail.fetcher import fetch_message, list_message_ids, FULL_HEADERS


def test_fetch_message_builds_emailmessage():
    service = MagicMock()
    service.users().messages().get().execute.return_value = {
        "id": "m1",
        "snippet": "hello there",
        "payload": {"headers": [
            {"name": "Subject", "value": "Hi"},
            {"name": "From", "value": "a@b.com"},
            {"name": "X-Spam-Status", "value": "Yes"},
        ]},
    }
    email = fetch_message(service, "m1")
    assert email.id == "m1"
    assert email.subject == "Hi"
    assert email.sender == "a@b.com"
    assert email.headers["X-Spam-Status"] == "Yes"
    assert email.snippet == "hello there"


def test_fetch_message_missing_subject_defaults():
    service = MagicMock()
    service.users().messages().get().execute.return_value = {"id": "m2", "snippet": "", "payload": {"headers": []}}
    email = fetch_message(service, "m2")
    assert email.subject == "(no subject)"


def test_list_message_ids_paginates():
    service = MagicMock()
    service.users().messages().list().execute.side_effect = [
        {"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "p2"},
        {"messages": [{"id": "c"}]},
    ]
    ids = list_message_ids(service, "after:2026/01/01")
    assert ids == ["a", "b", "c"]


def test_full_headers_includes_spam_status():
    assert "X-Spam-Status" in FULL_HEADERS

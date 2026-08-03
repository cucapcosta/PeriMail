from unittest.mock import MagicMock
from peribot.mail.labeler import replace_label, perimail_label_ids


def _service_with_labels(labels):
    service = MagicMock()
    service.users().labels().list().execute.return_value = {"labels": labels}
    return service


def test_perimail_label_ids_filters_by_prefix():
    service = _service_with_labels([
        {"id": "1", "name": "PeriMail/Jobs"},
        {"id": "2", "name": "INBOX"},
        {"id": "3", "name": "PeriMail/Spam"},
    ])
    assert perimail_label_ids(service) == {"1", "3"}


def test_replace_label_removes_perimail_adds_new():
    service = MagicMock()
    replace_label(service, "msg1", "new_id", {"old1", "old2", "new_id"})
    service.users().messages().modify.assert_called_once()
    _, kwargs = service.users().messages().modify.call_args
    body = kwargs["body"]
    assert body["addLabelIds"] == ["new_id"]
    assert set(body["removeLabelIds"]) == {"old1", "old2"}
    assert kwargs["id"] == "msg1"

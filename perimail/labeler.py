def ensure_label_exists(service, label_path: str) -> str:
    """Returns the Gmail label ID for label_path, creating it if it doesn't exist."""
    try:
        labels = service.users().labels().list(userId="me").execute().get("labels", [])
    except Exception as exc:
        raise RuntimeError(f"Failed to list Gmail labels: {exc}") from exc
    for label in labels:
        if label["name"] == label_path:
            return label["id"]

    result = service.users().labels().create(
        userId="me",
        body={
            "name": label_path,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    ).execute()
    return result["id"]


def apply_label(service, message_id: str, label_id: str) -> None:
    """Applies label_id to the Gmail message identified by message_id."""
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": [label_id]},
    ).execute()


def perimail_label_ids(service) -> set:
    """Returns the set of Gmail label IDs whose name starts with 'PeriMail/'."""
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    return {lbl["id"] for lbl in labels if lbl["name"].startswith("PeriMail/")}


def replace_label(service, message_id: str, new_label_id: str, perimail_ids: set) -> None:
    """Removes every PeriMail/* label, then adds new_label_id."""
    remove = [lid for lid in perimail_ids if lid != new_label_id]
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": [new_label_id], "removeLabelIds": remove},
    ).execute()

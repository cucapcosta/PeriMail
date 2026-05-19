from perimail.fetcher import EmailMessage

UNCLASSIFIED = "Unclassified"


def classify_by_rules(email: EmailMessage, categories: list) -> str | None:
    """
    Classify an email by matching against category rules.

    Checks headers first (case-insensitive), then keywords in subject + sender.
    Returns the name of the first matching category, or None if no match.
    """
    email_headers_lower = {k.lower() for k in email.headers}
    text = f"{email.subject} {email.sender}".lower()

    for category in categories:
        # Check header triggers first
        for header in category.header_triggers:
            if header.lower() in email_headers_lower:
                return category.name
        # Then check keywords
        for keyword in category.keywords:
            if keyword.lower() in text:
                return category.name

    return None

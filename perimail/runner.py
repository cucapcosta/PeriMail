from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC

from perimail.auth import get_credentials, get_gmail_service
from perimail.classifier import classify
from perimail.crypto import decrypt
from perimail.db import Database
from perimail.fetcher import fetch_new_emails
from perimail.labeler import apply_label, ensure_label_exists

UNCLASSIFIED_LABEL = "PeriMail/Unclassified"


@dataclass
class AccountResult:
    email: str
    category_counts: dict = field(default_factory=dict)
    rules_count: int = 0
    gemini_count: int = 0
    failed_count: int = 0


async def run_account(account, db: Database, gemini_api_key: str, encryption_key: bytes) -> AccountResult:
    result = AccountResult(email=account.email)

    tokens_json = decrypt(account.encrypted_tokens, encryption_key)
    # Token/credential failures propagate intentionally — abort this account's run
    credentials = get_credentials(tokens_json)
    service = get_gmail_service(credentials)

    categories = await db.get_categories(account.account_type)

    label_ids = {}
    for cat in categories:
        label_ids[cat.name] = ensure_label_exists(service, cat.label)
    label_ids[UNCLASSIFIED_LABEL] = ensure_label_exists(service, UNCLASSIFIED_LABEL)

    since_date = (datetime.now(UTC) - timedelta(hours=48)).strftime("%Y/%m/%d")
    emails = fetch_new_emails(service, since_date)

    for email in emails:
        if await db.is_processed(email.id, account.email):
            continue

        try:
            category_name, method = classify(email, categories, gemini_api_key)
        except Exception:
            result.failed_count += 1
            await db.mark_processed(email.id, account.email, "Unclassified", "error")
            continue

        label_id = label_ids.get(category_name, label_ids[UNCLASSIFIED_LABEL])
        apply_label(service, email.id, label_id)
        await db.mark_processed(email.id, account.email, category_name, method)

        result.category_counts[category_name] = result.category_counts.get(category_name, 0) + 1
        if method == "rules":
            result.rules_count += 1
        else:
            result.gemini_count += 1

    return result


async def run_all(db: Database, gemini_api_key: str, encryption_key: bytes) -> dict:
    accounts = await db.list_accounts()
    results = {}
    for account in accounts:
        results[account.email] = await run_account(account, db, gemini_api_key, encryption_key)
    return results

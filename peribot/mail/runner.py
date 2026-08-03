from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC

from peribot.mail import pricing
from peribot.mail.auth import get_credentials, get_gmail_service
from peribot.mail.classifier import classify, UNCLASSIFIED
from peribot.mail.crypto import decrypt
from peribot.mail.db import Database
from peribot.mail.fetcher import fetch_new_emails
from peribot.mail.inferrer import infer
from peribot.mail.labeler import apply_label, ensure_label_exists, perimail_label_ids, replace_label
from peribot.mail.scorer import score_urgency

UNCLASSIFIED_LABEL = "PeriMail/Unclassified"


@dataclass
class AccountResult:
    email: str
    category_counts: dict = field(default_factory=dict)
    rules_count: int = 0
    gemini_count: int = 0
    failed_count: int = 0
    gemini_picks: list = field(default_factory=list)   # (subject, category)
    urgent: list = field(default_factory=list)          # (score, subject)
    reassigned_count: int = 0
    proposals_count: int = 0


async def _record(db, call_type, usage):
    if usage and (usage.input_tokens or usage.output_tokens):
        await db.record_usage(pricing.MODEL, call_type, usage.input_tokens, usage.output_tokens)


async def run_account(account, db: Database, gemini_api_key: str, encryption_key: bytes, run_inference: bool = True) -> AccountResult:
    result = AccountResult(email=account.email)

    tokens_json = decrypt(account.encrypted_tokens, encryption_key)
    credentials = get_credentials(tokens_json)
    service = get_gmail_service(credentials)

    categories = await db.get_categories(account.account_type)
    cat_by_name = {c.name: c for c in categories}

    label_ids = {}
    for cat in categories:
        label_ids[cat.name] = ensure_label_exists(service, cat.label)
    label_ids[UNCLASSIFIED] = ensure_label_exists(service, UNCLASSIFIED_LABEL)
    all_perimail_ids = set(label_ids.values())

    since_date = (datetime.now(UTC) - timedelta(hours=48)).strftime("%Y/%m/%d")
    emails = fetch_new_emails(service, since_date)

    unclassified = []

    for email in emails:
        if await db.is_processed(email.id, account.email):
            continue

        try:
            category_name, method, usage = classify(email, categories, gemini_api_key)
        except Exception:
            result.failed_count += 1
            await db.mark_processed(email.id, account.email, UNCLASSIFIED, "error", subject=email.subject)
            continue

        await _record(db, "classify", usage)

        label_id = label_ids.get(category_name, label_ids[UNCLASSIFIED])
        apply_label(service, email.id, label_id)
        await db.mark_processed(email.id, account.email, category_name, method, subject=email.subject)

        result.category_counts[category_name] = result.category_counts.get(category_name, 0) + 1
        if method == "rules":
            result.rules_count += 1
        else:
            result.gemini_count += 1
            result.gemini_picks.append((email.subject, category_name))

        cat = cat_by_name.get(category_name)
        if cat and cat.score_urgency:
            score, reason, susage = score_urgency(email, gemini_api_key)
            await _record(db, "score", susage)
            if score is not None:
                await db.set_urgency(email.id, account.email, score)
                result.urgent.append((score, email.subject))

        if category_name == UNCLASSIFIED:
            unclassified.append(email)

    if run_inference and unclassified:
        reassignments, proposals, iusage = infer(unclassified, categories, gemini_api_key)
        await _record(db, "infer", iusage)
        email_by_id = {e.id: e for e in unclassified}

        for r in reassignments:
            mid, cname = r["message_id"], r["category"]
            if cname in label_ids and mid in email_by_id:
                replace_label(service, mid, label_ids[cname], all_perimail_ids)
                await db.update_processed_category(mid, account.email, cname, "infer")
                result.reassigned_count += 1
                result.category_counts[UNCLASSIFIED] = max(0, result.category_counts.get(UNCLASSIFIED, 0) - 1)
                result.category_counts[cname] = result.category_counts.get(cname, 0) + 1

        for p in proposals:
            samples = [
                {"subject": email_by_id[mid].subject, "message_id": mid, "account_email": account.email}
                for mid in p.get("sample_message_ids", []) if mid in email_by_id
            ]
            await db.add_proposal(p["name"], p.get("description", ""), p.get("keywords", []), samples)
            result.proposals_count += 1

    return result


async def run_all(db: Database, gemini_api_key: str, encryption_key: bytes) -> dict:
    accounts = await db.list_accounts()
    results = {}
    for account in accounts:
        results[account.email] = await run_account(account, db, gemini_api_key, encryption_key)
    return results

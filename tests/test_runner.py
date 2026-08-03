import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from peribot.mail.db import Account, Category, Database
from peribot.mail.fetcher import EmailMessage
from peribot.mail.runner import AccountResult, run_account

DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping PostgreSQL tests"
)


@pytest.fixture
async def db():
    d = Database(DATABASE_URL)
    await d.connect()
    yield d
    async with d._pool.acquire() as conn:
        await conn.execute("DELETE FROM processed_messages WHERE account_email LIKE 'test%'")
        await conn.execute("DELETE FROM accounts WHERE email LIKE 'test%'")
    await d.close()


@pytest.fixture
def account():
    import base64, os as _os
    from peribot.mail.crypto import encrypt
    key = _os.urandom(32)
    tokens = json.dumps({
        "token": "tok", "refresh_token": "rtok",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cid", "client_secret": "csec",
        "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
    })
    encrypted = encrypt(tokens, key)
    return Account(id=1, email="test@gmail.com", account_type="personal",
                   encrypted_tokens=encrypted, registered_at="2026-01-01"), key


async def test_run_account_labels_new_emails(db, account, mocker):
    acct, key = account
    email = EmailMessage(id="m1", subject="Internship at Acme", sender="hr@acme.com", snippet="")
    mocker.patch("peribot.mail.runner.get_credentials", return_value=MagicMock())
    mocker.patch("peribot.mail.runner.get_gmail_service", return_value=MagicMock())
    mocker.patch("peribot.mail.runner.fetch_new_emails", return_value=[email])
    mocker.patch("peribot.mail.runner.ensure_label_exists", return_value="label_id_jobs")
    mocker.patch("peribot.mail.runner.apply_label")
    from peribot.mail.pricing import Usage
    mocker.patch("peribot.mail.runner.classify", return_value=("Jobs", "rules", Usage()))
    mocker.patch("peribot.mail.runner.score_urgency", return_value=(None, "", Usage()))
    mocker.patch("peribot.mail.runner.infer", return_value=([], [], Usage()))

    result = await run_account(acct, db, gemini_api_key="fake", encryption_key=key)

    assert result.category_counts.get("Jobs") == 1
    assert result.rules_count == 1
    assert result.gemini_count == 0
    assert await db.is_processed("m1", "test@gmail.com")


async def test_run_account_skips_already_processed(db, account, mocker):
    acct, key = account
    await db.mark_processed("test_m1", "test@gmail.com", "Jobs", "rules")
    email = EmailMessage(id="test_m1", subject="Internship at Acme", sender="hr@acme.com", snippet="")
    mocker.patch("peribot.mail.runner.get_credentials", return_value=MagicMock())
    mocker.patch("peribot.mail.runner.get_gmail_service", return_value=MagicMock())
    mocker.patch("peribot.mail.runner.fetch_new_emails", return_value=[email])
    mocker.patch("peribot.mail.runner.ensure_label_exists", return_value="label_id")
    apply_mock = mocker.patch("peribot.mail.runner.apply_label")
    classify_mock = mocker.patch("peribot.mail.runner.classify")
    mocker.patch("peribot.mail.runner.infer", return_value=([], [], None))

    result = await run_account(acct, db, gemini_api_key="fake", encryption_key=key)

    apply_mock.assert_not_called()
    classify_mock.assert_not_called()
    assert result.category_counts == {}


async def test_run_account_counts_failed_on_classify_error(db, account, mocker):
    acct, key = account
    email = EmailMessage(id="test_m2", subject="Something", sender="x@y.com", snippet="")
    mocker.patch("peribot.mail.runner.get_credentials", return_value=MagicMock())
    mocker.patch("peribot.mail.runner.get_gmail_service", return_value=MagicMock())
    mocker.patch("peribot.mail.runner.fetch_new_emails", return_value=[email])
    mocker.patch("peribot.mail.runner.ensure_label_exists", return_value="label_id")
    mocker.patch("peribot.mail.runner.apply_label")
    mocker.patch("peribot.mail.runner.classify", side_effect=Exception("Gemini down"))
    mocker.patch("peribot.mail.runner.infer", return_value=([], [], None))

    result = await run_account(acct, db, gemini_api_key="fake", encryption_key=key)
    assert result.failed_count == 1


async def test_run_account_scores_urgency_for_flagged_category(db, account, mocker):
    acct, key = account
    email = EmailMessage(id="m_urg", subject="Invoice due", sender="billing@x.com", snippet="pay now")
    mocker.patch("peribot.mail.runner.get_credentials", return_value=MagicMock())
    mocker.patch("peribot.mail.runner.get_gmail_service", return_value=MagicMock())
    mocker.patch("peribot.mail.runner.fetch_new_emails", return_value=[email])
    mocker.patch("peribot.mail.runner.ensure_label_exists", return_value="lid")
    mocker.patch("peribot.mail.runner.apply_label")
    from peribot.mail.pricing import Usage
    mocker.patch("peribot.mail.runner.classify", return_value=("Useful", "rules", Usage()))
    score_mock = mocker.patch("peribot.mail.runner.score_urgency", return_value=(5, "urgent", Usage(5, 1)))
    mocker.patch("peribot.mail.runner.infer", return_value=([], [], Usage()))

    result = await run_account(acct, db, gemini_api_key="fake", encryption_key=key)
    score_mock.assert_called_once()
    assert (5, "Invoice due") in result.urgent

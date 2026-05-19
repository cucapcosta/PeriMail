import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from perimail.db import Account, Category, Database
from perimail.fetcher import EmailMessage
from perimail.runner import AccountResult, run_account


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    yield d
    await d.close()


@pytest.fixture
def account():
    import base64, os as _os
    from perimail.crypto import encrypt
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
    mocker.patch("perimail.runner.get_credentials", return_value=MagicMock())
    mocker.patch("perimail.runner.get_gmail_service", return_value=MagicMock())
    mocker.patch("perimail.runner.fetch_new_emails", return_value=[email])
    mocker.patch("perimail.runner.ensure_label_exists", return_value="label_id_jobs")
    mocker.patch("perimail.runner.apply_label")
    mocker.patch("perimail.runner.classify", return_value=("Jobs", "rules"))

    result = await run_account(acct, db, gemini_api_key="fake", encryption_key=key)

    assert result.category_counts.get("Jobs") == 1
    assert result.rules_count == 1
    assert result.gemini_count == 0
    assert await db.is_processed("m1", "test@gmail.com")


async def test_run_account_skips_already_processed(db, account, mocker):
    acct, key = account
    await db.mark_processed("m1", "test@gmail.com", "Jobs", "rules")

    email = EmailMessage(id="m1", subject="Internship at Acme", sender="hr@acme.com", snippet="")
    mocker.patch("perimail.runner.get_credentials", return_value=MagicMock())
    mocker.patch("perimail.runner.get_gmail_service", return_value=MagicMock())
    mocker.patch("perimail.runner.fetch_new_emails", return_value=[email])
    mocker.patch("perimail.runner.ensure_label_exists", return_value="label_id")
    apply_mock = mocker.patch("perimail.runner.apply_label")

    result = await run_account(acct, db, gemini_api_key="fake", encryption_key=key)

    apply_mock.assert_not_called()
    assert result.category_counts == {}


async def test_run_account_counts_failed_on_classify_error(db, account, mocker):
    acct, key = account

    email = EmailMessage(id="m2", subject="Something", sender="x@y.com", snippet="")
    mocker.patch("perimail.runner.get_credentials", return_value=MagicMock())
    mocker.patch("perimail.runner.get_gmail_service", return_value=MagicMock())
    mocker.patch("perimail.runner.fetch_new_emails", return_value=[email])
    mocker.patch("perimail.runner.ensure_label_exists", return_value="label_id")
    mocker.patch("perimail.runner.apply_label")
    mocker.patch("perimail.runner.classify", side_effect=Exception("Gemini down"))

    result = await run_account(acct, db, gemini_api_key="fake", encryption_key=key)

    assert result.failed_count == 1

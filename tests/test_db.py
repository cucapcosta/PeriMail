import os
import pytest
from perimail.db import Database

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
        await conn.execute("DELETE FROM categories WHERE name NOT IN ('Spam', 'Newsletter', 'Jobs', 'Useful')")
        await conn.execute("DELETE FROM settings")
    await d.close()


async def test_default_categories_seeded(db):
    cats = await db.list_categories()
    names = [c.name for c in cats]
    assert set(names) >= {"Spam", "Newsletter", "Jobs", "Useful"}


async def test_add_and_get_account(db):
    await db.add_account("test@gmail.com", "personal", "tok")
    account = await db.get_account("test@gmail.com")
    assert account is not None
    assert account.email == "test@gmail.com"
    assert account.account_type == "personal"
    assert account.encrypted_tokens == "tok"


async def test_remove_account(db):
    await db.add_account("test_gone@gmail.com", "professional", "tok")
    await db.remove_account("test_gone@gmail.com")
    assert await db.get_account("test_gone@gmail.com") is None


async def test_list_accounts(db):
    await db.add_account("test_a@gmail.com", "personal", "t1")
    await db.add_account("test_b@gmail.com", "professional", "t2")
    accounts = await db.list_accounts()
    emails = [a.email for a in accounts]
    assert "test_a@gmail.com" in emails
    assert "test_b@gmail.com" in emails


async def test_add_and_remove_category(db):
    await db.add_category("Events", "PeriMail/Events", "Event invitations", ["invitation", "rsvp"], [], "all")
    cats = await db.list_categories()
    assert any(c.name == "Events" for c in cats)
    await db.remove_category("Events")
    cats = await db.list_categories()
    assert not any(c.name == "Events" for c in cats)


async def test_get_categories_filters_by_type(db):
    await db.add_category("ProfOnly", "PeriMail/ProfOnly", "Professionals only", [], [], "professional")
    personal_cats = await db.get_categories("personal")
    prof_cats = await db.get_categories("professional")
    assert not any(c.name == "ProfOnly" for c in personal_cats)
    assert any(c.name == "ProfOnly" for c in prof_cats)


async def test_get_categories_requires_account_type(db):
    # Verify that get_categories requires explicit account_type parameter
    try:
        await db.get_categories()
        assert False, "get_categories should require account_type parameter"
    except TypeError:
        pass  # Expected


async def test_mark_and_check_processed(db):
    await db.mark_processed("msg_001", "test@gmail.com", "Jobs", "rules")
    assert await db.is_processed("msg_001", "test@gmail.com")
    assert not await db.is_processed("msg_002", "test@gmail.com")


async def test_get_stats_since(db):
    from datetime import datetime, timedelta, UTC
    await db.mark_processed("test_m1", "test@gmail.com", "Jobs", "rules")
    await db.mark_processed("test_m2", "test@gmail.com", "Jobs", "gemini")
    await db.mark_processed("test_m3", "test@gmail.com", "Newsletter", "rules")
    since = datetime.now(UTC) - timedelta(minutes=1)
    stats = await db.get_stats_since("test@gmail.com", since)
    assert stats["Jobs"] == 2
    assert stats["Newsletter"] == 1


async def test_update_account_tokens(db):
    await db.add_account("test_upd@gmail.com", "personal", "old_token")
    await db.update_account_tokens("test_upd@gmail.com", "new_token")
    account = await db.get_account("test_upd@gmail.com")
    assert account.encrypted_tokens == "new_token"


async def test_set_and_get_default_calendar(db):
    await db.set_default_calendar("12345", "user@gmail.com")
    result = await db.get_default_calendar("12345")
    assert result == "user@gmail.com"


async def test_get_default_calendar_returns_none_when_missing(db):
    result = await db.get_default_calendar("99999")
    assert result is None


async def test_set_default_calendar_overwrites(db):
    await db.set_default_calendar("12345", "first@gmail.com")
    await db.set_default_calendar("12345", "second@gmail.com")
    result = await db.get_default_calendar("12345")
    assert result == "second@gmail.com"

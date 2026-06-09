import os
from datetime import datetime, UTC
import pytest
from perimail.db import Database

DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set")


@pytest.fixture
async def db():
    d = Database(DATABASE_URL)
    await d.connect()
    # Purge before yield too: other test files (e.g. test_runner) write api_usage
    # rows via their own fixtures and don't clean it, which would pollute the
    # month-usage assertion below if they ran first.
    async with d._pool.acquire() as conn:
        await conn.execute("DELETE FROM api_usage")
        await conn.execute("DELETE FROM category_proposals")
    yield d
    async with d._pool.acquire() as conn:
        await conn.execute("DELETE FROM api_usage")
        await conn.execute("DELETE FROM category_proposals")
        await conn.execute("DELETE FROM processed_messages WHERE account_email LIKE 'test%'")
    await d.close()


async def test_record_and_get_month_usage(db):
    await db.record_usage("gemini-3.5-flash", "classify", 100, 20)
    await db.record_usage("gemini-3.5-flash", "score", 50, 10)
    rows = await db.get_month_usage(datetime.now(UTC))
    total = {"input": 0, "output": 0, "calls": 0}
    for r in rows:
        total["input"] += r["input_tokens"]
        total["output"] += r["output_tokens"]
        total["calls"] += r["calls"]
    assert total == {"input": 150, "output": 30, "calls": 2}


async def test_mark_processed_with_subject_and_urgency(db):
    await db.mark_processed("test_x1", "test@x.com", "Useful", "rules", subject="Invoice 42")
    await db.set_urgency("test_x1", "test@x.com", 5)
    rows = await db.list_unclassified("test@x.com")
    assert rows == []


async def test_list_unclassified_returns_subject(db):
    await db.mark_processed("test_u1", "test@x.com", "Unclassified", "gemini", subject="Mystery mail")
    rows = await db.list_unclassified("test@x.com")
    assert any(r["message_id"] == "test_u1" and r["subject"] == "Mystery mail" for r in rows)


async def test_update_processed_category(db):
    await db.mark_processed("test_r1", "test@x.com", "Unclassified", "gemini", subject="Steam sale")
    await db.update_processed_category("test_r1", "test@x.com", "Games", "infer")
    rows = await db.list_unclassified("test@x.com")
    assert all(r["message_id"] != "test_r1" for r in rows)


async def test_proposal_lifecycle(db):
    await db.add_proposal("Games", "gaming mail", ["steam"],
                          [{"subject": "Steam sale", "message_id": "m1", "account_email": "test@x.com"}])
    pending = await db.list_pending_proposals_without_message()
    assert len(pending) == 1
    pid = pending[0].id
    assert pending[0].samples[0]["message_id"] == "m1"
    await db.mark_proposal_posted(pid, "discord123")
    assert await db.list_pending_proposals_without_message() == []
    p = await db.get_proposal(pid)
    assert p.discord_message_id == "discord123"
    await db.set_proposal_status(pid, "approved")
    assert (await db.get_proposal(pid)).status == "approved"

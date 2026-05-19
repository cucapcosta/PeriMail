import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import aiosqlite

DB_PATH = os.environ.get("DB_PATH", "perimail.db")


@dataclass
class Account:
    id: int
    email: str
    account_type: str
    encrypted_tokens: str
    registered_at: str


@dataclass
class Category:
    id: int
    name: str
    label: str
    description: str
    keywords: list
    header_triggers: list
    applies_to: str


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._init_schema()

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _init_schema(self):
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                account_type TEXT NOT NULL,
                encrypted_tokens TEXT NOT NULL,
                registered_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                label TEXT NOT NULL,
                description TEXT NOT NULL,
                keywords TEXT NOT NULL DEFAULT '[]',
                header_triggers TEXT NOT NULL DEFAULT '[]',
                applies_to TEXT NOT NULL DEFAULT 'all'
            );
            CREATE TABLE IF NOT EXISTS processed_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                account_email TEXT NOT NULL,
                category TEXT NOT NULL,
                classified_by TEXT NOT NULL,
                classified_at TEXT NOT NULL,
                UNIQUE(message_id, account_email)
            );
        """)
        await self._conn.commit()
        await self._seed_default_categories()

    async def _seed_default_categories(self):
        row = await self._fetchone("SELECT COUNT(*) as c FROM categories")
        if row["c"] > 0:
            return
        defaults = [
            ("Spam", "PeriMail/Spam", "Unwanted emails, phishing, unsolicited messages", [], [], "all"),
            ("Newsletter", "PeriMail/Newsletter", "Marketing emails, digests, subscription updates", [], ["List-Unsubscribe", "List-Id"], "all"),
            ("Jobs", "PeriMail/Jobs", "Job offers, internship opportunities, application status, recruiting emails", ["internship", "application received", "hiring", "offer letter", "job offer", "we received your application", "your application"], [], "all"),
            ("Useful", "PeriMail/Useful", "Important emails that require attention or action", [], [], "all"),
        ]
        for name, label, desc, keywords, headers, applies_to in defaults:
            await self._conn.execute(
                "INSERT OR IGNORE INTO categories (name, label, description, keywords, header_triggers, applies_to) VALUES (?,?,?,?,?,?)",
                (name, label, desc, json.dumps(keywords), json.dumps(headers), applies_to),
            )
        await self._conn.commit()

    async def _fetchone(self, sql, params=()):
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def _fetchall(self, sql, params=()):
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchall()

    # --- Accounts ---

    async def add_account(self, email: str, account_type: str, encrypted_tokens: str):
        await self._conn.execute(
            "INSERT INTO accounts (email, account_type, encrypted_tokens, registered_at) VALUES (?,?,?,?)",
            (email, account_type, encrypted_tokens, datetime.utcnow().isoformat()),
        )
        await self._conn.commit()

    async def get_account(self, email: str) -> Optional[Account]:
        row = await self._fetchone("SELECT * FROM accounts WHERE email=?", (email,))
        return Account(**dict(row)) if row else None

    async def list_accounts(self) -> list:
        rows = await self._fetchall("SELECT * FROM accounts")
        return [Account(**dict(row)) for row in rows]

    async def update_account_tokens(self, email: str, encrypted_tokens: str):
        await self._conn.execute(
            "UPDATE accounts SET encrypted_tokens=? WHERE email=?",
            (encrypted_tokens, email),
        )
        await self._conn.commit()

    async def remove_account(self, email: str):
        await self._conn.execute("DELETE FROM accounts WHERE email=?", (email,))
        await self._conn.commit()

    # --- Categories ---

    async def add_category(self, name: str, label: str, description: str, keywords: list, header_triggers: list, applies_to: str):
        await self._conn.execute(
            "INSERT INTO categories (name, label, description, keywords, header_triggers, applies_to) VALUES (?,?,?,?,?,?)",
            (name, label, description, json.dumps(keywords), json.dumps(header_triggers), applies_to),
        )
        await self._conn.commit()

    async def get_categories(self, account_type: str = "all") -> list:
        rows = await self._fetchall(
            "SELECT * FROM categories WHERE applies_to='all' OR applies_to=?",
            (account_type,),
        )
        return [self._row_to_category(row) for row in rows]

    async def list_categories(self) -> list:
        rows = await self._fetchall("SELECT * FROM categories")
        return [self._row_to_category(row) for row in rows]

    async def remove_category(self, name: str):
        await self._conn.execute("DELETE FROM categories WHERE name=?", (name,))
        await self._conn.commit()

    def _row_to_category(self, row) -> Category:
        d = dict(row)
        d["keywords"] = json.loads(d["keywords"])
        d["header_triggers"] = json.loads(d["header_triggers"])
        return Category(**d)

    # --- Processed Messages ---

    async def is_processed(self, message_id: str, account_email: str) -> bool:
        row = await self._fetchone(
            "SELECT 1 FROM processed_messages WHERE message_id=? AND account_email=?",
            (message_id, account_email),
        )
        return row is not None

    async def mark_processed(self, message_id: str, account_email: str, category: str, classified_by: str):
        await self._conn.execute(
            "INSERT OR IGNORE INTO processed_messages (message_id, account_email, category, classified_by, classified_at) VALUES (?,?,?,?,?)",
            (message_id, account_email, category, classified_by, datetime.utcnow().isoformat()),
        )
        await self._conn.commit()

    async def get_stats_since(self, account_email: str, since: datetime) -> dict:
        rows = await self._fetchall(
            "SELECT category, COUNT(*) as count FROM processed_messages WHERE account_email=? AND classified_at>=? GROUP BY category",
            (account_email, since.isoformat()),
        )
        return {row["category"]: row["count"] for row in rows}

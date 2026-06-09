import json
import os
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Optional

import asyncpg


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
    score_urgency: bool = False


@dataclass
class Proposal:
    id: int
    name: str
    description: str
    keywords: list
    samples: list           # list of {subject, message_id, account_email}
    status: str
    discord_message_id: Optional[str]


class Database:
    def __init__(self, dsn: str = None):
        self._dsn = dsn or os.environ["DATABASE_URL"]
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        self._pool = await asyncpg.create_pool(self._dsn)
        await self._init_schema()

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _init_schema(self):
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    account_type TEXT NOT NULL,
                    encrypted_tokens TEXT NOT NULL,
                    registered_at TIMESTAMP NOT NULL
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    label TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    keywords TEXT NOT NULL DEFAULT '[]',
                    header_triggers TEXT NOT NULL DEFAULT '[]',
                    applies_to TEXT NOT NULL DEFAULT 'all'
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_messages (
                    id SERIAL PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    account_email TEXT NOT NULL,
                    category TEXT NOT NULL,
                    classified_by TEXT NOT NULL,
                    classified_at TIMESTAMP NOT NULL,
                    UNIQUE(message_id, account_email)
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    discord_user_id TEXT PRIMARY KEY,
                    default_calendar_email TEXT
                );
            """)
            await conn.execute(
                "ALTER TABLE categories ADD COLUMN IF NOT EXISTS score_urgency BOOLEAN NOT NULL DEFAULT false"
            )
            await conn.execute(
                "ALTER TABLE processed_messages ADD COLUMN IF NOT EXISTS subject TEXT"
            )
            await conn.execute(
                "ALTER TABLE processed_messages ADD COLUMN IF NOT EXISTS urgency_score INT"
            )
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS api_usage (
                    id SERIAL PRIMARY KEY,
                    model TEXT NOT NULL,
                    call_type TEXT NOT NULL,
                    input_tokens INT NOT NULL,
                    output_tokens INT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS category_proposals (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    keywords TEXT NOT NULL DEFAULT '[]',
                    samples TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'pending',
                    discord_message_id TEXT,
                    created_at TIMESTAMP NOT NULL
                );
            """)
        await self._seed_default_categories()

    async def _seed_default_categories(self):
        defaults = [
            (
                "Spam", "PeriMail/Spam",
                "Spam and junk emails",
                '["spam","junk","bulk mail","click here","free offer","limited time","win","congratulations","unsubscribe",'
                '"lixo","oferta grátis","tempo limitado","ganhou","parabéns","promoção","descadastrar","clique aqui"]',
                '["X-Spam-Status"]', "all", False,
            ),
            (
                "Newsletter", "PeriMail/Newsletter",
                "Newsletters and mailing lists",
                '["newsletter","mailing list","weekly digest","monthly update","edition","subscribe",'
                '"boletim","lista de emails","atualização semanal","edição","assinar","cancelar assinatura"]',
                '["List-Unsubscribe", "List-Id"]', "all", False,
            ),
            (
                "Jobs", "PeriMail/Jobs",
                "Job offers, internship applications, and recruitment emails",
                '["internship","job offer","application received","your application","recruitment","hiring","vacancy","career","position",'
                '"estágio","oferta de emprego","candidatura recebida","sua candidatura","recrutamento","contratação","vaga","carreira","trainee"]',
                "[]", "all", True,
            ),
            (
                "Useful", "PeriMail/Useful",
                "Important and useful emails such as invoices, receipts, bookings, confirmations",
                '["invoice","receipt","ticket","reservation","confirmation","booking","deadline","urgent","password reset","verification","order",'
                '"fatura","recibo","ingresso","reserva","confirmação","reserva","prazo","urgente","redefinir senha","verificação","pedido"]',
                "[]", "all", True,
            ),
        ]
        async with self._pool.acquire() as conn:
            for name, label, desc, keywords, headers, applies_to, score_urgency in defaults:
                await conn.execute(
                    """INSERT INTO categories (name, label, description, keywords, header_triggers, applies_to, score_urgency)
                       VALUES ($1,$2,$3,$4,$5,$6,$7)
                       ON CONFLICT (name) DO UPDATE SET keywords=EXCLUDED.keywords,
                           header_triggers=EXCLUDED.header_triggers, score_urgency=EXCLUDED.score_urgency""",
                    name, label, desc, keywords, headers, applies_to, score_urgency,
                )

    # --- Accounts ---

    async def add_account(self, email: str, account_type: str, encrypted_tokens: str):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO accounts (email, account_type, encrypted_tokens, registered_at) VALUES ($1,$2,$3,$4)",
                email, account_type, encrypted_tokens, datetime.now(UTC).replace(tzinfo=None),
            )

    async def get_account(self, email: str) -> Optional[Account]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM accounts WHERE email=$1", email)
        return self._row_to_account(row) if row else None

    async def list_accounts(self) -> list:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM accounts")
        return [self._row_to_account(row) for row in rows]

    async def update_account_tokens(self, email: str, encrypted_tokens: str):
        async with self._pool.acquire() as conn:
            status = await conn.execute(
                "UPDATE accounts SET encrypted_tokens=$1 WHERE email=$2",
                encrypted_tokens, email,
            )
        if status == "UPDATE 0":
            raise ValueError(f"No account found for {email}")

    async def remove_account(self, email: str):
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM accounts WHERE email=$1", email)

    def _row_to_account(self, row) -> Account:
        return Account(
            id=row["id"],
            email=row["email"],
            account_type=row["account_type"],
            encrypted_tokens=row["encrypted_tokens"],
            registered_at=str(row["registered_at"]),
        )

    # --- Categories ---

    async def add_category(self, name: str, label: str, description: str, keywords: list, header_triggers: list, applies_to: str):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO categories (name, label, description, keywords, header_triggers, applies_to) VALUES ($1,$2,$3,$4,$5,$6)",
                name, label, description, json.dumps(keywords), json.dumps(header_triggers), applies_to,
            )

    async def get_categories(self, account_type: str) -> list:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM categories WHERE applies_to='all' OR applies_to=$1",
                account_type,
            )
        return [self._row_to_category(row) for row in rows]

    async def list_categories(self) -> list:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM categories")
        return [self._row_to_category(row) for row in rows]

    async def remove_category(self, name: str):
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM categories WHERE name=$1", name)

    def _row_to_category(self, row) -> Category:
        return Category(
            id=row["id"],
            name=row["name"],
            label=row["label"],
            description=row["description"],
            keywords=json.loads(row["keywords"]),
            header_triggers=json.loads(row["header_triggers"]),
            applies_to=row["applies_to"],
            score_urgency=row["score_urgency"],
        )

    # --- Processed Messages ---

    async def is_processed(self, message_id: str, account_email: str) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM processed_messages WHERE message_id=$1 AND account_email=$2",
                message_id, account_email,
            )
        return row is not None

    async def mark_processed(self, message_id: str, account_email: str, category: str, classified_by: str, subject: str = None):
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO processed_messages (message_id, account_email, category, classified_by, classified_at, subject)
                   VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (message_id, account_email)
                   DO UPDATE SET category=EXCLUDED.category, classified_by=EXCLUDED.classified_by,
                       classified_at=EXCLUDED.classified_at, subject=COALESCE(EXCLUDED.subject, processed_messages.subject)""",
                message_id, account_email, category, classified_by,
                datetime.now(UTC).replace(tzinfo=None), subject,
            )

    async def get_stats_since(self, account_email: str, since: datetime) -> dict:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT category, COUNT(*) as count FROM processed_messages WHERE account_email=$1 AND classified_at>=$2 GROUP BY category",
                account_email, since,
            )
        return {row["category"]: row["count"] for row in rows}

    async def set_urgency(self, message_id: str, account_email: str, score: int):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE processed_messages SET urgency_score=$1 WHERE message_id=$2 AND account_email=$3",
                score, message_id, account_email,
            )

    async def update_processed_category(self, message_id: str, account_email: str, category: str, classified_by: str):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE processed_messages SET category=$1, classified_by=$2 WHERE message_id=$3 AND account_email=$4",
                category, classified_by, message_id, account_email,
            )

    async def list_unclassified(self, account_email: str = None) -> list:
        async with self._pool.acquire() as conn:
            if account_email:
                rows = await conn.fetch(
                    "SELECT message_id, account_email, subject FROM processed_messages WHERE category='Unclassified' AND account_email=$1",
                    account_email,
                )
            else:
                rows = await conn.fetch(
                    "SELECT message_id, account_email, subject FROM processed_messages WHERE category='Unclassified'"
                )
        return [dict(r) for r in rows]

    # --- API Usage ---

    async def record_usage(self, model: str, call_type: str, input_tokens: int, output_tokens: int):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO api_usage (model, call_type, input_tokens, output_tokens, created_at) VALUES ($1,$2,$3,$4,$5)",
                model, call_type, input_tokens, output_tokens, datetime.now(UTC).replace(tzinfo=None),
            )

    async def get_month_usage(self, now: datetime) -> list:
        month_start = datetime(now.year, now.month, 1)
        next_month = datetime(now.year + 1, 1, 1) if now.month == 12 else datetime(now.year, now.month + 1, 1)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT model, SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens, COUNT(*) AS calls
                   FROM api_usage WHERE created_at >= $1 AND created_at < $2 GROUP BY model""",
                month_start, next_month,
            )
        return [{"model": r["model"], "input_tokens": int(r["input_tokens"]),
                 "output_tokens": int(r["output_tokens"]), "calls": int(r["calls"])} for r in rows]

    # --- Category Proposals ---

    async def add_proposal(self, name: str, description: str, keywords: list, samples: list):
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO category_proposals (name, description, keywords, samples, status, created_at)
                   VALUES ($1,$2,$3,$4,'pending',$5)""",
                name, description, json.dumps(keywords), json.dumps(samples),
                datetime.now(UTC).replace(tzinfo=None),
            )

    async def list_pending_proposals_without_message(self) -> list:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM category_proposals WHERE status='pending' AND discord_message_id IS NULL"
            )
        return [self._row_to_proposal(r) for r in rows]

    async def get_proposal(self, proposal_id: int):
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM category_proposals WHERE id=$1", proposal_id)
        return self._row_to_proposal(row) if row else None

    async def mark_proposal_posted(self, proposal_id: int, discord_message_id: str):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE category_proposals SET discord_message_id=$1 WHERE id=$2",
                discord_message_id, proposal_id,
            )

    async def set_proposal_status(self, proposal_id: int, status: str):
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE category_proposals SET status=$1 WHERE id=$2", status, proposal_id,
            )

    def _row_to_proposal(self, row) -> Proposal:
        return Proposal(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            keywords=json.loads(row["keywords"]),
            samples=json.loads(row["samples"]),
            status=row["status"],
            discord_message_id=row["discord_message_id"],
        )

    # --- Settings ---

    async def get_default_calendar(self, discord_user_id: str) -> Optional[str]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT default_calendar_email FROM settings WHERE discord_user_id=$1",
                discord_user_id,
            )
        return row["default_calendar_email"] if row else None

    async def set_default_calendar(self, discord_user_id: str, email: str):
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO settings (discord_user_id, default_calendar_email) VALUES ($1,$2)
                   ON CONFLICT (discord_user_id) DO UPDATE SET default_calendar_email=EXCLUDED.default_calendar_email""",
                discord_user_id, email,
            )

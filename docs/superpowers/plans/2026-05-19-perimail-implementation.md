# PeriMailOrg Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-hosted, open-source Gmail organizer that classifies emails daily via rule engine + Gemini 2.5 Flash fallback, applies Gmail labels, and is fully configured through a Discord bot.

**Architecture:** Two Python processes share a SQLite database. The cron process (`main.py`) runs daily at 7am — fetches new emails per account, classifies them, sends a Discord DM report. The bot process (`bot/bot.py`) runs always-on as a Discord bot + aiohttp OAuth callback server, handling all user configuration via slash commands.

**Tech Stack:** Python 3.11+, `discord.py` 2.3+, `aiohttp` 3.9+, `google-api-python-client` 2.x, `google-auth-oauthlib` 1.x, `google-generativeai` 0.8+, `cryptography` 42+, `aiosqlite` 0.20+, `python-dotenv` 1.x, `pytest`, `pytest-asyncio` (asyncio_mode=auto), `pytest-mock`

---

## File Map

```
perimail/
├── perimail/
│   ├── __init__.py
│   ├── db.py            # SQLite schema, CRUD for accounts/categories/processed_messages
│   ├── crypto.py        # AES-256-GCM encrypt/decrypt for OAuth tokens
│   ├── auth.py          # Gmail OAuth2: generate URL, exchange code, build credentials
│   ├── fetcher.py       # fetch new emails via Gmail API → list[EmailMessage]
│   ├── classifier.py    # rule engine + Gemini 2.5 Flash fallback → (category, method)
│   ├── labeler.py       # ensure Gmail label exists, apply label to message
│   ├── runner.py        # orchestrate fetch→classify→label per account → AccountResult
│   └── report.py        # build Discord DM report string from run results
├── bot/
│   ├── __init__.py
│   ├── bot.py           # Discord bot entrypoint, loads cogs, starts OAuth server
│   ├── oauth_server.py  # aiohttp server: /oauth/callback, /health, pending state dict
│   └── commands/
│       ├── __init__.py
│       ├── accounts.py  # /add-account (interactive), /remove-account, /list-accounts
│       ├── categories.py# /add-category (interactive), /remove-category, /list-categories
│       └── run.py       # /run-now
├── tests/
│   ├── __init__.py
│   ├── test_db.py
│   ├── test_crypto.py
│   ├── test_classifier.py
│   └── test_report.py
├── main.py              # cron entrypoint: run_all → send Discord DM report
├── Dockerfile
├── Procfile
├── railway.toml
├── .env.example
└── pyproject.toml
```

---

## Task 1: Project Setup

**Files:**
- Create: `pyproject.toml`
- Create: `Dockerfile`
- Create: `Procfile`
- Create: `railway.toml`
- Create: `.env.example`
- Create: `perimail/__init__.py`, `bot/__init__.py`, `bot/commands/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "perimail"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "google-auth>=2.29.0",
    "google-auth-oauthlib>=1.2.0",
    "google-api-python-client>=2.127.0",
    "google-generativeai>=0.8.0",
    "discord.py>=2.3.2",
    "aiohttp>=3.9.5",
    "cryptography>=42.0.5",
    "aiosqlite>=0.20.0",
    "python-dotenv>=1.0.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.6",
    "pytest-mock>=3.14.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["perimail*", "bot*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Write Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[dev]"
COPY . .

CMD ["python", "bot/bot.py"]
```

- [ ] **Step 3: Write Procfile**

```
bot: python bot/bot.py
cron: python main.py
```

- [ ] **Step 4: Write railway.toml**

```toml
[build]
builder = "DOCKERFILE"

[deploy]
startCommand = "python bot/bot.py"
healthcheckPath = "/health"
healthcheckTimeout = 10
```

Note for users: Create a second Railway service from the same repo with `startCommand = "python main.py"` and enable the Cron Job service type with schedule `0 7 * * *`.

- [ ] **Step 5: Write .env.example**

```
DISCORD_BOT_TOKEN=
DISCORD_USER_ID=
GEMINI_API_KEY=
ENCRYPTION_KEY=        # base64-encoded 32 bytes: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
RAILWAY_PUBLIC_URL=    # e.g. https://your-app.up.railway.app
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
DB_PATH=perimail.db    # optional, defaults to perimail.db
PORT=8080              # optional, defaults to 8080
```

- [ ] **Step 6: Create empty __init__.py files**

```bash
touch perimail/__init__.py bot/__init__.py bot/commands/__init__.py tests/__init__.py
```

- [ ] **Step 7: Install deps and verify**

```bash
pip install -e ".[dev]"
pytest --collect-only
```

Expected: 0 tests collected, no errors.

- [ ] **Step 8: Commit**

```bash
git init
git add pyproject.toml Dockerfile Procfile railway.toml .env.example perimail/__init__.py bot/__init__.py bot/commands/__init__.py tests/__init__.py
git commit -m "chore: project scaffold"
```

---

## Task 2: Database Layer

**Files:**
- Create: `perimail/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_db.py
import pytest
from perimail.db import Database


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    yield d
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
    await db.add_account("gone@gmail.com", "professional", "tok")
    await db.remove_account("gone@gmail.com")
    assert await db.get_account("gone@gmail.com") is None


async def test_list_accounts(db):
    await db.add_account("a@gmail.com", "personal", "t1")
    await db.add_account("b@gmail.com", "professional", "t2")
    accounts = await db.list_accounts()
    emails = [a.email for a in accounts]
    assert "a@gmail.com" in emails
    assert "b@gmail.com" in emails


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


async def test_mark_and_check_processed(db):
    await db.mark_processed("msg_001", "test@gmail.com", "Jobs", "rules")
    assert await db.is_processed("msg_001", "test@gmail.com")
    assert not await db.is_processed("msg_002", "test@gmail.com")


async def test_get_stats_since(db):
    from datetime import datetime, timedelta
    await db.mark_processed("m1", "test@gmail.com", "Jobs", "rules")
    await db.mark_processed("m2", "test@gmail.com", "Jobs", "gemini")
    await db.mark_processed("m3", "test@gmail.com", "Newsletter", "rules")
    since = datetime.utcnow() - timedelta(minutes=1)
    stats = await db.get_stats_since("test@gmail.com", since)
    assert stats["Jobs"] == 2
    assert stats["Newsletter"] == 1


async def test_update_account_tokens(db):
    await db.add_account("upd@gmail.com", "personal", "old_token")
    await db.update_account_tokens("upd@gmail.com", "new_token")
    account = await db.get_account("upd@gmail.com")
    assert account.encrypted_tokens == "new_token"
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'perimail.db'`

- [ ] **Step 3: Implement perimail/db.py**

```python
# perimail/db.py
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
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
pytest tests/test_db.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add perimail/db.py tests/test_db.py
git commit -m "feat: database layer with schema, account/category/message CRUD"
```

---

## Task 3: Crypto Layer

**Files:**
- Create: `perimail/crypto.py`
- Create: `tests/test_crypto.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_crypto.py
import os
import pytest
from perimail.crypto import decrypt, encrypt


@pytest.fixture
def key():
    return os.urandom(32)


def test_encrypt_decrypt_roundtrip(key):
    plaintext = '{"access_token": "ya29.xxx", "refresh_token": "1//yyy"}'
    assert decrypt(encrypt(plaintext, key), key) == plaintext


def test_different_ciphertexts_same_plaintext(key):
    token1 = encrypt("same", key)
    token2 = encrypt("same", key)
    assert token1 != token2  # different random nonces


def test_wrong_key_raises(key):
    token = encrypt("secret", key)
    with pytest.raises(Exception):
        decrypt(token, os.urandom(32))


def test_tampered_ciphertext_raises(key):
    token = encrypt("secret", key)
    tampered = token[:-4] + "XXXX"
    with pytest.raises(Exception):
        decrypt(tampered, key)
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
pytest tests/test_crypto.py -v
```

Expected: `ModuleNotFoundError: No module named 'perimail.crypto'`

- [ ] **Step 3: Implement perimail/crypto.py**

```python
# perimail/crypto.py
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def get_encryption_key() -> bytes:
    raw = os.environ["ENCRYPTION_KEY"]
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise ValueError(f"ENCRYPTION_KEY must decode to 32 bytes, got {len(key)}")
    return key


def encrypt(plaintext: str, key: bytes) -> str:
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str, key: bytes) -> str:
    data = base64.b64decode(token.encode("ascii"))
    nonce, ciphertext = data[:12], data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
pytest tests/test_crypto.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add perimail/crypto.py tests/test_crypto.py
git commit -m "feat: AES-256-GCM encrypt/decrypt for OAuth token storage"
```

---

## Task 4: Gmail Auth

**Files:**
- Create: `perimail/auth.py`

No unit tests here — the OAuth flow requires real Google endpoints. Integration-tested manually during the OAuth flow in Task 13.

- [ ] **Step 1: Implement perimail/auth.py**

```python
# perimail/auth.py
import json
import os
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def _client_config() -> dict:
    redirect_uri = f"{os.environ['RAILWAY_PUBLIC_URL']}/oauth/callback"
    return {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


def generate_auth_url(state: str) -> str:
    config = _client_config()
    flow = Flow.from_client_config(config, scopes=SCOPES)
    flow.redirect_uri = config["web"]["redirect_uris"][0]
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )
    return auth_url


def exchange_code(code: str) -> tuple:
    """Returns (tokens_dict, email_address)."""
    config = _client_config()
    flow = Flow.from_client_config(config, scopes=SCOPES)
    flow.redirect_uri = config["web"]["redirect_uris"][0]
    flow.fetch_token(code=code)
    creds = flow.credentials

    service = build("oauth2", "v2", credentials=creds)
    user_info = service.userinfo().get().execute()
    email = user_info["email"]

    tokens = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }
    return tokens, email


def get_credentials(tokens_json: str) -> Credentials:
    tokens = json.loads(tokens_json)
    return Credentials(
        token=tokens["token"],
        refresh_token=tokens["refresh_token"],
        token_uri=tokens["token_uri"],
        client_id=tokens["client_id"],
        client_secret=tokens["client_secret"],
        scopes=tokens["scopes"],
    )


def get_gmail_service(credentials: Credentials):
    return build("gmail", "v1", credentials=credentials)
```

- [ ] **Step 2: Commit**

```bash
git add perimail/auth.py
git commit -m "feat: Gmail OAuth2 flow — generate URL, exchange code, build credentials"
```

---

## Task 5: Email Fetcher

**Files:**
- Create: `perimail/fetcher.py`

- [ ] **Step 1: Implement perimail/fetcher.py**

No unit test for fetcher — it wraps the Gmail API. Mock-based tests would test only the mock, not behavior. Test via integration when running `/run-now` in Task 15.

```python
# perimail/fetcher.py
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class EmailMessage:
    id: str
    subject: str
    sender: str
    snippet: str
    headers: dict = field(default_factory=dict)


def fetch_new_emails(service, since_date: str = None) -> list:
    """
    Fetch emails since since_date (format: YYYY/MM/DD).
    Defaults to last 48 hours.
    Returns list[EmailMessage] with metadata only (no body).
    """
    if since_date is None:
        since_dt = datetime.utcnow() - timedelta(hours=48)
        since_date = since_dt.strftime("%Y/%m/%d")

    query = f"after:{since_date}"
    emails = []
    page_token = None

    while True:
        kwargs = {"userId": "me", "q": query, "maxResults": 500}
        if page_token:
            kwargs["pageToken"] = page_token

        result = service.users().messages().list(**kwargs).execute()
        messages = result.get("messages", [])

        for msg_ref in messages:
            msg = service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="metadata",
                metadataHeaders=["Subject", "From", "List-Unsubscribe", "List-Id"],
            ).execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            emails.append(EmailMessage(
                id=msg["id"],
                subject=headers.get("Subject", "(no subject)"),
                sender=headers.get("From", ""),
                snippet=msg.get("snippet", ""),
                headers=headers,
            ))

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return emails
```

- [ ] **Step 2: Commit**

```bash
git add perimail/fetcher.py
git commit -m "feat: Gmail email fetcher with metadata-only fetch and pagination"
```

---

## Task 6: Rule Engine

**Files:**
- Create: `perimail/classifier.py` (rule engine only)
- Create: `tests/test_classifier.py` (rule engine tests only)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_classifier.py
import pytest
from perimail.classifier import classify_by_rules
from perimail.db import Category
from perimail.fetcher import EmailMessage


def make_category(name, keywords=None, header_triggers=None, applies_to="all"):
    return Category(
        id=1, name=name, label=f"PeriMail/{name}",
        description=f"{name} emails",
        keywords=keywords or [],
        header_triggers=header_triggers or [],
        applies_to=applies_to,
    )


def make_email(subject="Hello", sender="sender@example.com", snippet="", headers=None):
    return EmailMessage(id="msg1", subject=subject, sender=sender, snippet=snippet, headers=headers or {})


def test_keyword_match_in_subject():
    cats = [make_category("Jobs", keywords=["internship"])]
    email = make_email(subject="Internship opportunity at Acme")
    assert classify_by_rules(email, cats) == "Jobs"


def test_keyword_match_case_insensitive():
    cats = [make_category("Jobs", keywords=["application received"])]
    email = make_email(subject="Application Received - Software Engineer")
    assert classify_by_rules(email, cats) == "Jobs"


def test_keyword_match_in_sender():
    cats = [make_category("Newsletter", keywords=["noreply"])]
    email = make_email(sender="noreply@company.com")
    assert classify_by_rules(email, cats) == "Newsletter"


def test_header_trigger_match():
    cats = [make_category("Newsletter", header_triggers=["List-Unsubscribe"])]
    email = make_email(headers={"List-Unsubscribe": "<mailto:unsub@example.com>"})
    assert classify_by_rules(email, cats) == "Newsletter"


def test_header_match_case_insensitive():
    cats = [make_category("Newsletter", header_triggers=["list-unsubscribe"])]
    email = make_email(headers={"List-Unsubscribe": "<mailto:unsub@example.com>"})
    assert classify_by_rules(email, cats) == "Newsletter"


def test_no_match_returns_none():
    cats = [make_category("Jobs", keywords=["internship"])]
    email = make_email(subject="Meeting tomorrow")
    assert classify_by_rules(email, cats) is None


def test_first_category_wins():
    cats = [
        make_category("Newsletter", keywords=["update"]),
        make_category("Jobs", keywords=["update"]),
    ]
    email = make_email(subject="Job update for you")
    assert classify_by_rules(email, cats) == "Newsletter"
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
pytest tests/test_classifier.py -v
```

Expected: `ModuleNotFoundError: No module named 'perimail.classifier'`

- [ ] **Step 3: Implement rule engine in perimail/classifier.py**

```python
# perimail/classifier.py
from perimail.fetcher import EmailMessage

UNCLASSIFIED = "Unclassified"


def classify_by_rules(email: EmailMessage, categories: list) -> str | None:
    email_headers_lower = {k.lower() for k in email.headers}
    text = f"{email.subject} {email.sender}".lower()

    for category in categories:
        for header in category.header_triggers:
            if header.lower() in email_headers_lower:
                return category.name
        for keyword in category.keywords:
            if keyword.lower() in text:
                return category.name

    return None
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
pytest tests/test_classifier.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add perimail/classifier.py tests/test_classifier.py
git commit -m "feat: rule engine — header trigger and keyword matching"
```

---

## Task 7: Gemini Classifier + Integrate

**Files:**
- Modify: `perimail/classifier.py` (add Gemini + top-level classify())
- Modify: `tests/test_classifier.py` (add Gemini + classify() tests)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_classifier.py`:

```python
# append to tests/test_classifier.py
from unittest.mock import MagicMock, patch
from perimail.classifier import classify, classify_with_gemini


def test_classify_uses_rules_first():
    cats = [make_category("Jobs", keywords=["internship"])]
    email = make_email(subject="Internship offer")
    category, method = classify(email, cats, api_key="fake")
    assert category == "Jobs"
    assert method == "rules"


def test_classify_falls_back_to_gemini_when_no_rule_matches(mocker):
    cats = [make_category("Jobs", keywords=["internship"])]
    email = make_email(subject="Some unrelated subject")
    mocker.patch("perimail.classifier.classify_with_gemini", return_value="Useful")
    category, method = classify(email, cats, api_key="fake")
    assert category == "Useful"
    assert method == "gemini"


def test_classify_with_gemini_returns_valid_category(mocker):
    cats = [make_category("Jobs"), make_category("Newsletter")]
    email = make_email(subject="We received your application")

    mock_model = MagicMock()
    mock_model.generate_content.return_value.text = "Jobs"
    mocker.patch("google.generativeai.GenerativeModel", return_value=mock_model)
    mocker.patch("google.generativeai.configure")

    result = classify_with_gemini(email, cats, api_key="fake_key")
    assert result == "Jobs"


def test_classify_with_gemini_returns_unclassified_on_invalid_response(mocker):
    cats = [make_category("Jobs")]
    email = make_email(subject="Something")

    mock_model = MagicMock()
    mock_model.generate_content.return_value.text = "WeirdResponse"
    mocker.patch("google.generativeai.GenerativeModel", return_value=mock_model)
    mocker.patch("google.generativeai.configure")

    result = classify_with_gemini(email, cats, api_key="fake_key")
    assert result == "Unclassified"


def test_classify_with_gemini_retries_on_exception(mocker):
    cats = [make_category("Jobs")]
    email = make_email(subject="Something")

    mock_model = MagicMock()
    mock_model.generate_content.side_effect = [Exception("API error"), Exception("API error"), Exception("API error")]
    mocker.patch("google.generativeai.GenerativeModel", return_value=mock_model)
    mocker.patch("google.generativeai.configure")
    mocker.patch("time.sleep")

    result = classify_with_gemini(email, cats, api_key="fake_key")
    assert result == "Unclassified"
    assert mock_model.generate_content.call_count == 3
```

- [ ] **Step 2: Run new tests, confirm they fail**

```bash
pytest tests/test_classifier.py -v -k "gemini or classify_uses or falls_back"
```

Expected: `ImportError` or `AttributeError` — `classify_with_gemini` and `classify` don't exist yet.

- [ ] **Step 3: Add Gemini classifier and classify() to perimail/classifier.py**

```python
# append to perimail/classifier.py
import time
import google.generativeai as genai


def classify_with_gemini(email: EmailMessage, categories: list, api_key: str) -> str:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    category_list = "\n".join(
        f"- {cat.name}: {cat.description}" for cat in categories
    )
    prompt = (
        "You are an email classifier. Classify the following email into exactly one of these categories:\n"
        f"{category_list}\n\n"
        f"Email:\nSubject: {email.subject}\nFrom: {email.sender}\n"
        f"Snippet: {email.snippet[:200]}\n\n"
        "Respond with only the category name, nothing else."
    )

    valid_names = {cat.name for cat in categories}
    last_error = None

    for attempt in range(3):
        try:
            response = model.generate_content(prompt)
            result = response.text.strip()
            if result in valid_names:
                return result
            for name in valid_names:
                if name.lower() == result.lower():
                    return name
            return UNCLASSIFIED
        except Exception as e:
            last_error = e
            if attempt < 2:
                time.sleep(2 ** attempt)

    return UNCLASSIFIED


def classify(email: EmailMessage, categories: list, api_key: str) -> tuple:
    """Returns (category_name, method) where method is 'rules' or 'gemini'."""
    result = classify_by_rules(email, categories)
    if result:
        return result, "rules"
    return classify_with_gemini(email, categories, api_key), "gemini"
```

- [ ] **Step 4: Run all classifier tests**

```bash
pytest tests/test_classifier.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add perimail/classifier.py tests/test_classifier.py
git commit -m "feat: Gemini 2.5 Flash classifier with 3-retry backoff and classify() orchestrator"
```

---

## Task 8: Gmail Labeler

**Files:**
- Create: `perimail/labeler.py`

No unit tests — wraps Gmail API. Tested via integration in Task 9 (runner).

- [ ] **Step 1: Implement perimail/labeler.py**

```python
# perimail/labeler.py


def ensure_label_exists(service, label_path: str) -> str:
    """Returns the Gmail label ID for label_path, creating it if it doesn't exist."""
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
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


def apply_label(service, message_id: str, label_id: str):
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": [label_id]},
    ).execute()
```

- [ ] **Step 2: Commit**

```bash
git add perimail/labeler.py
git commit -m "feat: Gmail labeler — ensure label exists, apply to message"
```

---

## Task 9: Runner

**Files:**
- Create: `perimail/runner.py`
- Create: `tests/test_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_runner.py
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
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
pytest tests/test_runner.py -v
```

Expected: `ModuleNotFoundError: No module named 'perimail.runner'`

- [ ] **Step 3: Implement perimail/runner.py**

```python
# perimail/runner.py
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

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
    credentials = get_credentials(tokens_json)
    service = get_gmail_service(credentials)

    categories = await db.get_categories(account.account_type)

    label_ids = {}
    for cat in categories:
        label_ids[cat.name] = ensure_label_exists(service, cat.label)
    label_ids[UNCLASSIFIED_LABEL] = ensure_label_exists(service, UNCLASSIFIED_LABEL)

    since_date = (datetime.utcnow() - timedelta(hours=48)).strftime("%Y/%m/%d")
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
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_runner.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add perimail/runner.py tests/test_runner.py
git commit -m "feat: runner orchestrates fetch→classify→label per account"
```

---

## Task 10: Report Builder

**Files:**
- Create: `perimail/report.py`
- Create: `tests/test_report.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_report.py
from datetime import datetime
from perimail.report import build_report
from perimail.runner import AccountResult


def test_report_contains_account_emails():
    results = {
        "personal@gmail.com": AccountResult(
            email="personal@gmail.com",
            category_counts={"Jobs": 3, "Newsletter": 5},
            rules_count=7, gemini_count=1, failed_count=0,
        ),
    }
    report = build_report(results, datetime(2026, 5, 19, 7, 0))
    assert "personal@gmail.com" in report
    assert "Jobs" in report
    assert "3" in report
    assert "Newsletter" in report
    assert "5" in report


def test_report_contains_totals():
    results = {
        "a@gmail.com": AccountResult(
            email="a@gmail.com",
            category_counts={"Spam": 2},
            rules_count=2, gemini_count=0, failed_count=1,
        ),
    }
    report = build_report(results, datetime(2026, 5, 19, 7, 0))
    assert "rules: 2" in report.lower() or "2" in report
    assert "failed: 1" in report.lower() or "1" in report


def test_report_no_accounts():
    report = build_report({}, datetime(2026, 5, 19, 7, 0))
    assert "No accounts" in report or "no accounts" in report.lower()


def test_report_includes_date():
    report = build_report({}, datetime(2026, 5, 19, 7, 0))
    assert "2026-05-19" in report
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
pytest tests/test_report.py -v
```

Expected: `ModuleNotFoundError: No module named 'perimail.report'`

- [ ] **Step 3: Implement perimail/report.py**

```python
# perimail/report.py
from datetime import datetime


def build_report(results: dict, run_time: datetime) -> str:
    header = f"**PeriMail Report — {run_time.strftime('%Y-%m-%d %H:%M')} UTC**"

    if not results:
        return f"{header}\n\nNo accounts registered."

    lines = [header, ""]
    total_rules = total_gemini = total_failed = 0

    for email, result in results.items():
        lines.append(f"**{email}**")
        if not result.category_counts:
            lines.append("  No new emails")
        else:
            for cat, count in sorted(result.category_counts.items()):
                lines.append(f"  {cat:<22} {count}")
        lines.append("")
        total_rules += result.rules_count
        total_gemini += result.gemini_count
        total_failed += result.failed_count

    lines.append(
        f"Classified by rules: {total_rules} | Gemini: {total_gemini} | Failed: {total_failed}"
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_report.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add perimail/report.py tests/test_report.py
git commit -m "feat: report builder formats daily classification summary"
```

---

## Task 11: Main Entrypoint

**Files:**
- Create: `main.py`

- [ ] **Step 1: Implement main.py**

```python
# main.py
import asyncio
import base64
import os
from datetime import datetime

import aiohttp
from dotenv import load_dotenv

from perimail.db import Database
from perimail.report import build_report
from perimail.runner import run_all

load_dotenv()


async def send_discord_dm(report: str):
    token = os.environ["DISCORD_BOT_TOKEN"]
    user_id = os.environ["DISCORD_USER_ID"]

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://discord.com/api/v10/users/@me/channels",
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json={"recipient_id": user_id},
        ) as resp:
            channel_id = (await resp.json())["id"]

        chunks = [report[i:i+1900] for i in range(0, len(report), 1900)]
        for chunk in chunks:
            await session.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
                json={"content": chunk},
            )


async def main():
    gemini_api_key = os.environ["GEMINI_API_KEY"]
    encryption_key = base64.b64decode(os.environ["ENCRYPTION_KEY"])

    db = Database()
    await db.connect()

    try:
        run_time = datetime.utcnow()
        results = await run_all(db, gemini_api_key, encryption_key)
        report = build_report(results, run_time)
        await send_discord_dm(report)
        print(report)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
git add main.py
git commit -m "feat: cron entrypoint — run classification and send Discord DM report"
```

---

## Task 12: OAuth Callback Server

**Files:**
- Create: `bot/oauth_server.py`

- [ ] **Step 1: Implement bot/oauth_server.py**

```python
# bot/oauth_server.py
import asyncio
import json
import os
import secrets
import time
from typing import Optional

from aiohttp import web

from perimail.auth import exchange_code
from perimail.crypto import encrypt


class OAuthServer:
    def __init__(self):
        self._pending: dict = {}  # state -> {discord_user_id, account_type, expires_at}
        self._db = None
        self._bot = None
        self._encryption_key: Optional[bytes] = None
        self._runner: Optional[web.AppRunner] = None

    def generate_state(self, discord_user_id: int, account_type: str) -> str:
        state = secrets.token_urlsafe(32)
        self._pending[state] = {
            "discord_user_id": discord_user_id,
            "account_type": account_type,
            "expires_at": time.time() + 300,
        }
        return state

    async def _handle_callback(self, request: web.Request) -> web.Response:
        code = request.rel_url.query.get("code")
        state = request.rel_url.query.get("state")
        error = request.rel_url.query.get("error")

        if error:
            return web.Response(status=400, text=f"Authorization failed: {error}")

        pending = self._pending.get(state)
        if not pending:
            return web.Response(status=400, text="Invalid or expired state. Run /add-account again.")

        if time.time() > pending["expires_at"]:
            del self._pending[state]
            return web.Response(status=400, text="Link expired. Run /add-account again.")

        del self._pending[state]

        try:
            loop = asyncio.get_running_loop()
            tokens, email = await loop.run_in_executor(None, exchange_code, code)
            encrypted = encrypt(json.dumps(tokens), self._encryption_key)
            await self._db.add_account(email, pending["account_type"], encrypted)

            user = await self._bot.fetch_user(pending["discord_user_id"])
            await user.send(f"Account `{email}` ({pending['account_type']}) registered ✓")

            return web.Response(
                content_type="text/html",
                body="<html><body><h2>✓ Authorization successful!</h2><p>You can close this tab and return to Discord.</p></body></html>",
            )
        except Exception as e:
            return web.Response(status=500, text=f"Error during authorization: {e}")

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def start(self, db, bot, encryption_key: bytes):
        self._db = db
        self._bot = bot
        self._encryption_key = encryption_key

        port = int(os.environ.get("PORT", "8080"))
        app = web.Application()
        app.router.add_get("/oauth/callback", self._handle_callback)
        app.router.add_get("/health", self._handle_health)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", port)
        await site.start()
        print(f"OAuth server listening on port {port}")

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
```

- [ ] **Step 2: Commit**

```bash
git add bot/oauth_server.py
git commit -m "feat: OAuth callback server with CSRF state validation and TTL"
```

---

## Task 13: Bot Account Commands

**Files:**
- Create: `bot/commands/accounts.py`

- [ ] **Step 1: Implement bot/commands/accounts.py**

```python
# bot/commands/accounts.py
import asyncio
import os

import discord
from discord import app_commands
from discord.ext import commands

from perimail.auth import generate_auth_url


def _authorized(interaction: discord.Interaction) -> bool:
    return interaction.user.id == int(os.environ["DISCORD_USER_ID"])


class AccountsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="add-account", description="Register a Gmail account via OAuth")
    async def add_account(self, interaction: discord.Interaction):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        await interaction.response.send_message(
            "Account type? Reply with `personal` or `professional`:", ephemeral=True
        )

        channel = interaction.channel
        user_id = interaction.user.id

        def check(m: discord.Message) -> bool:
            return m.author.id == user_id and m.channel.id == channel.id

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=60.0)
            account_type = msg.content.strip().lower()
            if account_type not in ("personal", "professional"):
                await interaction.followup.send("Invalid type. Run `/add-account` again.", ephemeral=True)
                return
        except asyncio.TimeoutError:
            await interaction.followup.send("Timed out. Run `/add-account` again.", ephemeral=True)
            return

        state = self.bot.oauth_server.generate_state(user_id, account_type)
        url = generate_auth_url(state)
        await interaction.followup.send(
            f"Click this link to authorize Gmail access (expires in 5 minutes):\n{url}",
            ephemeral=True,
        )

    @app_commands.command(name="remove-account", description="Remove a registered Gmail account")
    async def remove_account(self, interaction: discord.Interaction):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        accounts = await self.bot.db.list_accounts()
        if not accounts:
            await interaction.response.send_message("No accounts registered.", ephemeral=True)
            return

        options = "\n".join(f"- `{a.email}` ({a.account_type})" for a in accounts)
        await interaction.response.send_message(
            f"Which account to remove? Reply with the email address:\n{options}", ephemeral=True
        )

        channel = interaction.channel
        user_id = interaction.user.id

        def check(m: discord.Message) -> bool:
            return m.author.id == user_id and m.channel.id == channel.id

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=60.0)
            email = msg.content.strip()
        except asyncio.TimeoutError:
            await interaction.followup.send("Timed out.", ephemeral=True)
            return

        if not any(a.email == email for a in accounts):
            await interaction.followup.send(f"`{email}` not found.", ephemeral=True)
            return

        await self.bot.db.remove_account(email)
        await interaction.followup.send(f"Account `{email}` removed.", ephemeral=True)

    @app_commands.command(name="list-accounts", description="List all registered Gmail accounts")
    async def list_accounts(self, interaction: discord.Interaction):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        accounts = await self.bot.db.list_accounts()
        if not accounts:
            await interaction.response.send_message("No accounts registered.", ephemeral=True)
            return

        lines = ["**Registered accounts:**"]
        for a in accounts:
            lines.append(f"- `{a.email}` ({a.account_type})")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AccountsCog(bot))
```

- [ ] **Step 2: Commit**

```bash
git add bot/commands/accounts.py
git commit -m "feat: Discord /add-account, /remove-account, /list-accounts commands"
```

---

## Task 14: Bot Category Commands

**Files:**
- Create: `bot/commands/categories.py`

- [ ] **Step 1: Implement bot/commands/categories.py**

```python
# bot/commands/categories.py
import asyncio
import os

import discord
from discord import app_commands
from discord.ext import commands


def _authorized(interaction: discord.Interaction) -> bool:
    return interaction.user.id == int(os.environ["DISCORD_USER_ID"])


class CategoriesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="add-category", description="Add a new email classification category")
    async def add_category(self, interaction: discord.Interaction):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        channel = interaction.channel
        user_id = interaction.user.id

        def check(m: discord.Message) -> bool:
            return m.author.id == user_id and m.channel.id == channel.id

        async def ask(prompt: str) -> str:
            await channel.send(prompt)
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=60.0)
                return msg.content.strip()
            except asyncio.TimeoutError:
                await channel.send("Timed out. Run `/add-category` again.")
                raise

        await interaction.response.send_message("**New Category — answer the following questions:**", ephemeral=False)

        try:
            name = await ask("**1/5** Category name (e.g. `Invoices`):")
            label = await ask(f"**2/5** Gmail label path (e.g. `PeriMail/{name}`):")
            description = await ask("**3/5** Description for AI classification (e.g. `Invoice and billing emails`):")
            keywords_raw = await ask("**4/5** Keywords, comma-separated (or `none`):")
            applies_raw = await ask("**5/5** Apply to which accounts? (`all`, `personal`, or `professional`):")
        except asyncio.TimeoutError:
            return

        keywords = [] if keywords_raw.lower() == "none" else [k.strip() for k in keywords_raw.split(",") if k.strip()]
        applies_to = applies_raw.lower()
        if applies_to not in ("all", "personal", "professional"):
            await channel.send("Invalid value for applies_to. Category not created.")
            return

        await self.bot.db.add_category(name, label, description, keywords, [], applies_to)
        await channel.send(f"Category **{name}** (`{label}`) created ✓\nApplies to: {applies_to} | Keywords: {keywords or 'none'}")

    @app_commands.command(name="remove-category", description="Remove an email category")
    async def remove_category(self, interaction: discord.Interaction):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        cats = await self.bot.db.list_categories()
        if not cats:
            await interaction.response.send_message("No categories.", ephemeral=True)
            return

        options = "\n".join(f"- `{c.name}`" for c in cats)
        await interaction.response.send_message(
            f"Which category to remove? Reply with the name:\n{options}", ephemeral=True
        )

        channel = interaction.channel
        user_id = interaction.user.id

        def check(m: discord.Message) -> bool:
            return m.author.id == user_id and m.channel.id == channel.id

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=60.0)
            name = msg.content.strip()
        except asyncio.TimeoutError:
            await interaction.followup.send("Timed out.", ephemeral=True)
            return

        if not any(c.name == name for c in cats):
            await interaction.followup.send(f"`{name}` not found.", ephemeral=True)
            return

        await self.bot.db.remove_category(name)
        await interaction.followup.send(f"Category `{name}` removed.", ephemeral=True)

    @app_commands.command(name="list-categories", description="List all email categories")
    async def list_categories(self, interaction: discord.Interaction):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        cats = await self.bot.db.list_categories()
        if not cats:
            await interaction.response.send_message("No categories defined.", ephemeral=True)
            return

        lines = ["**Categories:**"]
        for c in cats:
            kw = ", ".join(c.keywords) if c.keywords else "none"
            lines.append(f"**{c.name}** (`{c.label}`) — {c.applies_to}\n  > {c.description}\n  Keywords: {kw}")
        await interaction.response.send_message("\n\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CategoriesCog(bot))
```

- [ ] **Step 2: Commit**

```bash
git add bot/commands/categories.py
git commit -m "feat: Discord /add-category (interactive), /remove-category, /list-categories commands"
```

---

## Task 15: Bot Run Command

**Files:**
- Create: `bot/commands/run.py`

- [ ] **Step 1: Implement bot/commands/run.py**

```python
# bot/commands/run.py
import base64
import os
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from perimail.report import build_report
from perimail.runner import run_all


def _authorized(interaction: discord.Interaction) -> bool:
    return interaction.user.id == int(os.environ["DISCORD_USER_ID"])


class RunCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="run-now", description="Run email classification immediately")
    async def run_now(self, interaction: discord.Interaction):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        await interaction.response.send_message("Running classification...", ephemeral=True)

        try:
            results = await run_all(
                self.bot.db,
                os.environ["GEMINI_API_KEY"],
                self.bot.encryption_key,
            )
            report = build_report(results, datetime.utcnow())
            chunks = [report[i:i+1900] for i in range(0, len(report), 1900)]
            await interaction.followup.send(chunks[0], ephemeral=True)
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RunCog(bot))
```

- [ ] **Step 2: Commit**

```bash
git add bot/commands/run.py
git commit -m "feat: Discord /run-now command triggers classification on demand"
```

---

## Task 16: Bot Main + Wiring

**Files:**
- Create: `bot/bot.py`

- [ ] **Step 1: Implement bot/bot.py**

```python
# bot/bot.py
import asyncio
import base64
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from bot.oauth_server import OAuthServer
from perimail.db import Database

load_dotenv()


class PeriMailBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # Required for wait_for message content — enable in Discord Developer Portal
        super().__init__(command_prefix="!", intents=intents)
        self.db = Database()
        self.oauth_server = OAuthServer()
        self.encryption_key = base64.b64decode(os.environ["ENCRYPTION_KEY"])

    async def setup_hook(self):
        await self.load_extension("bot.commands.accounts")
        await self.load_extension("bot.commands.categories")
        await self.load_extension("bot.commands.run")
        await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")


async def main():
    bot = PeriMailBot()

    await bot.db.connect()
    await bot.oauth_server.start(bot.db, bot, bot.encryption_key)

    try:
        async with bot:
            await bot.start(os.environ["DISCORD_BOT_TOKEN"])
    finally:
        await bot.db.close()
        await bot.oauth_server.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run final test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Smoke-test bot locally**

Set env vars in `.env`, then:
```bash
python bot/bot.py
```

Expected output:
```
OAuth server listening on port 8080
Logged in as PeriMailBot#XXXX (ID: ...)
```

- [ ] **Step 4: Commit**

```bash
git add bot/bot.py
git commit -m "feat: Discord bot main with OAuth server wired up and slash commands registered"
```

---

## Deployment Checklist

- [ ] Create Google Cloud project, enable Gmail API and OAuth2 API
- [ ] Create OAuth 2.0 credentials (Web application type), add `https://your-app.up.railway.app/oauth/callback` as authorized redirect URI
- [ ] Generate `ENCRYPTION_KEY`: `python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"`
- [ ] Create Discord application + bot at discord.com/developers, enable **Message Content Intent**
- [ ] Create two Railway services from this repo:
  - **Bot service**: `startCommand = "python bot/bot.py"`, health check at `/health`
  - **Cron service**: enable Cron Job type, `command = "python main.py"`, schedule `0 7 * * *`
- [ ] Set all env vars from `.env.example` in both Railway services
- [ ] Run `/add-account` in Discord to register Gmail accounts
- [ ] Run `/run-now` to verify classification works end-to-end

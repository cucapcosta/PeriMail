# PeriMailOrg — Gmail Organizer Design

**Date:** 2026-05-19
**Status:** Approved

---

## Overview

Self-hosted, open-source Gmail organizer. Runs daily at 7am, classifies emails across multiple registered Gmail accounts using a rule engine with Gemini 2.5 Flash fallback, applies Gmail labels, and sends a daily summary report via Discord DM.

Each user hosts their own instance (Railway recommended). All configuration — accounts, categories — is managed through a Discord bot. No config files edited manually.

---

## Goals

- Classify emails into user-defined categories (default: Spam, Newsletter, Jobs, Useful)
- Apply Gmail labels, inbox untouched
- Support multiple Gmail accounts; categories can be scoped to `all`, `personal`, or `professional` account types
- Send daily Discord DM report after each run
- Allow managing accounts and categories entirely through Discord bot commands
- Open source, self-hosted, single-user-per-instance model

---

## Architecture

### Processes

Two long-running processes in one Railway service via `Procfile`:

- **`cron`** — `main.py` — scheduled daily at 7am, runs classification pipeline per account
- **`bot`** — `bot.py` — always-on Discord bot, handles commands and OAuth callback HTTP server

### Project Structure

```
perimail/
├── perimail/
│   ├── auth.py          # Gmail OAuth2: initiate flow, handle callback, refresh tokens
│   ├── fetcher.py       # fetch unprocessed emails via Gmail API
│   ├── classifier.py    # rule engine + Gemini 2.5 Flash fallback
│   ├── labeler.py       # apply Gmail labels via Gmail API
│   ├── runner.py        # orchestrate fetch → classify → label per account
│   ├── db.py            # SQLite access layer
│   ├── crypto.py        # encrypt/decrypt OAuth tokens at rest
│   └── report.py        # build and send Discord DM report
├── bot/
│   ├── bot.py           # Discord bot entrypoint, slash commands
│   ├── commands/
│   │   ├── accounts.py  # /add-account, /remove-account, /list-accounts
│   │   ├── categories.py# /add-category (interactive), /remove-category, /list-categories
│   │   └── run.py       # /run-now
│   └── oauth_server.py  # lightweight HTTP server for OAuth callback
├── main.py              # cron entrypoint
├── Dockerfile
├── Procfile
├── railway.toml
└── pyproject.toml
```

---

## Data Model (SQLite)

### `accounts`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| email | TEXT UNIQUE | |
| account_type | TEXT | `personal` or `professional` |
| encrypted_tokens | TEXT | AES-encrypted JSON OAuth tokens |
| registered_at | DATETIME | |

### `categories`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT UNIQUE | e.g. `Jobs` |
| label | TEXT | Gmail label path e.g. `PeriMail/Jobs` |
| description | TEXT | Used in Gemini prompt |
| keywords | TEXT | JSON array of keyword strings |
| header_triggers | TEXT | JSON array of header names e.g. `["List-Unsubscribe"]` |
| applies_to | TEXT | `all`, `personal`, or `professional` |

### `processed_messages`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| message_id | TEXT | Gmail message ID |
| account_email | TEXT | |
| category | TEXT | Assigned category name |
| classified_by | TEXT | `rules` or `gemini` |
| classified_at | DATETIME | |

---

## Default Categories

Seeded on first run if no categories exist:

| Name | Label | Applies To |
|---|---|---|
| Spam | `PeriMail/Spam` | all |
| Newsletter | `PeriMail/Newsletter` | all |
| Jobs | `PeriMail/Jobs` | all |
| Useful | `PeriMail/Useful` | all |

Users can add/remove/modify via bot at any time.

---

## Classification Pipeline

### 1. Rule Engine

For each email, checked in order:

1. **Header triggers** — if email has matching headers (e.g. `List-Unsubscribe`) → assign category
2. **Keyword match** — subject + sender checked against each category's keyword list
3. **First match wins** — categories checked in insertion order

If a rule matches → assign category, skip Gemini.

### 2. Gemini Fallback

Triggered when no rule matches.

**Input to Gemini (no full body — privacy + cost):**
- Subject
- Sender name + address
- Email snippet (first ~200 chars)
- Full list of category names + descriptions

**Model:** `gemini-2.5-flash`

**Retry:** Up to 3 attempts with exponential backoff (1s, 2s, 4s). If all fail → label `PeriMail/Unclassified`.

**Prompt structure:**
```
You are an email classifier. Classify the following email into exactly one of these categories:
{category list with descriptions}

Email:
Subject: {subject}
From: {sender}
Snippet: {snippet}

Respond with only the category name.
```

---

## Gmail OAuth Flow

1. User runs `/add-account` in Discord
2. Bot generates a random `state` token, stores it temporarily in memory with a TTL
3. Bot sends Google OAuth URL with `state` param and `redirect_uri` pointing to `RAILWAY_PUBLIC_URL/oauth/callback`
4. User clicks link, completes Google auth in browser
5. Google redirects to `/oauth/callback?code=...&state=...`
6. Callback validates `state`, exchanges code for tokens, encrypts tokens, saves to `accounts` table
7. Bot DMs user: "Account `email@example.com` registered ✓"

OAuth tokens are refreshed automatically before each run using the stored refresh token.

---

## Discord Bot Commands

### Account Management

| Command | Description |
|---|---|
| `/add-account` | Starts OAuth flow, sends link |
| `/remove-account` | Select from registered accounts to remove |
| `/list-accounts` | Show all registered accounts and types |

### Category Management

| Command | Description |
|---|---|
| `/add-category` | Interactive: bot asks name → label → description → keywords one at a time |
| `/remove-category` | Select from existing categories to remove |
| `/list-categories` | Show all categories with rules |

### Operations

| Command | Description |
|---|---|
| `/run-now` | Trigger classification immediately, bypassing schedule |

---

## Daily Report (Discord DM)

Sent after each cron run. Format:

```
PeriMail Report — 2026-05-19 07:00

account@personal.com
  Jobs         3
  Newsletter   12
  Spam         5
  Useful       2
  Unclassified 1

account@work.com
  Jobs         7
  Newsletter   4
  Useful       6

Classified by rules: 37 | Gemini: 3 | Failed: 1
```

If no new emails processed, still sends a brief "nothing new" message.

---

## Deployment (Railway)

### Procfile

```
cron: python main.py
bot: python bot/bot.py
```

### Required Environment Variables

| Variable | Description |
|---|---|
| `DISCORD_BOT_TOKEN` | Discord bot token |
| `DISCORD_USER_ID` | Your Discord user ID (for DMs and command auth) |
| `GEMINI_API_KEY` | Google Gemini API key |
| `ENCRYPTION_KEY` | 32-byte key for AES encryption of OAuth tokens |
| `RAILWAY_PUBLIC_URL` | Public URL of Railway service (for OAuth callback) |

### Railway Cron

Configured in `railway.toml` to trigger `main.py` daily at `0 7 * * *`.

### Estimated Cost

~$1–2.50/month Railway compute + negligible Gemini API cost (~$0.01–0.05/month). Well within Railway Hobby plan ($5/month credit).

---

## Security Considerations

- OAuth tokens encrypted at rest (AES-256) using `ENCRYPTION_KEY`
- OAuth state token validated on callback to prevent CSRF
- Discord commands restricted to `DISCORD_USER_ID` — no other user can interact with the bot
- No email body stored — only subject, sender, snippet sent to Gemini
- Gemini receives no PII beyond what's in the email header/snippet

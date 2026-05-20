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

    def new_state_token(self) -> str:
        self._pending = {s: v for s, v in self._pending.items() if time.time() < v["expires_at"]}
        return secrets.token_urlsafe(32)

    def register_state(self, state: str, discord_user_id: int, account_type: str, code_verifier: Optional[str]):
        self._pending[state] = {
            "discord_user_id": discord_user_id,
            "account_type": account_type,
            "expires_at": time.time() + 300,
            "code_verifier": code_verifier,
        }

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

        if not code:
            return web.Response(status=400, text="Missing authorization code. Run /add-account again.")

        try:
            loop = asyncio.get_running_loop()
            tokens, email = await loop.run_in_executor(None, exchange_code, code, pending.get("code_verifier"))
            encrypted = encrypt(json.dumps(tokens), self._encryption_key)
            await self._db.add_account(email, pending["account_type"], encrypted)

            user = await self._bot.fetch_user(pending["discord_user_id"])
            await user.send(f"Account `{email}` ({pending['account_type']}) registered ✓")

            return web.Response(
                content_type="text/html",
                text="<html><body><h2>✓ Authorization successful!</h2><p>You can close this tab and return to Discord.</p></body></html>",
            )
        except Exception as e:
            return web.Response(status=500, text=f"Authorization failed: {e}. Please run /add-account again.")

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

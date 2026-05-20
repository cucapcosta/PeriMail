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
        self.tree.allowed_installs = discord.app_commands.AppInstallationType(guild=True, user=True)
        self.tree.allowed_contexts = discord.app_commands.AppCommandContext(guild=True, bot_dm=True, private_channel=True)
        await self.load_extension("bot.commands.accounts")
        await self.load_extension("bot.commands.categories")
        await self.load_extension("bot.commands.run")
        await self.load_extension("bot.commands.calendar")
        await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        try:
            user = await self.fetch_user(int(os.environ["DISCORD_USER_ID"]))
            await user.send("👋 Peri is online and ready.")
        except Exception as e:
            print(f"Failed to send ready DM: {e}")


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

# main.py
import asyncio
import base64
import os
from datetime import datetime, UTC

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
        run_time = datetime.now(UTC)
        results = await run_all(db, gemini_api_key, encryption_key)
        report = build_report(results, run_time)
        await send_discord_dm(report)
        print(report)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())

import aiohttp


async def send_discord_dm(report: str, token: str, user_id: str) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://discord.com/api/v10/users/@me/channels",
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json={"recipient_id": user_id},
        ) as resp:
            resp.raise_for_status()
            channel_id = (await resp.json())["id"]

        chunks = [report[i:i+1900] for i in range(0, len(report), 1900)]
        for chunk in chunks:
            async with session.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
                json={"content": chunk},
            ) as chunk_resp:
                chunk_resp.raise_for_status()

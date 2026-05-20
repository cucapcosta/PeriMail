# bot/commands/run.py
import os
from datetime import datetime, UTC

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
            report = build_report(results, datetime.now(UTC))
            chunks = [report[i:i+1900] for i in range(0, len(report), 1900)] or ["(empty report)"]
            for chunk in chunks:
                await interaction.user.send(chunk)
            await interaction.followup.send("Report sent to DM.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RunCog(bot))

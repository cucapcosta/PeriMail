# bot/commands/run.py
import os
from datetime import datetime, UTC

import discord
from discord import app_commands
from discord.ext import commands

from peribot.core import pricing
from peribot.bot.progress import progress_bar, ThrottledEditor
from peribot.mail.report import build_report
from peribot.mail.runner import run_all


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
        status = await interaction.user.send("⏳ Classifying emails…")
        editor = ThrottledEditor(status)
        state = {}  # account email -> (done, total)

        async def on_progress(account_email, done, total):
            state[account_email] = (done, total)
            done_all = sum(d for d, _ in state.values())
            total_all = sum(t for _, t in state.values())
            content = f"⏳ Classifying emails…\n{progress_bar(done_all, total_all)}"
            current = next((e for e, (d, t) in state.items() if d < t), None)
            if current:
                content += f"\n-# {current}"
            await editor.update(content)

        try:
            run_time = datetime.now(UTC)
            results = await run_all(
                self.bot.db,
                os.environ["GEMINI_API_KEY"],
                self.bot.encryption_key,
                on_progress=on_progress,
            )
            done_all = sum(d for d, _ in state.values())
            total_all = sum(t for _, t in state.values())
            await editor.update(
                f"✅ Classification done — {done_all}/{total_all} emails processed. Report below.",
                force=True,
            )
            usage_rows = await self.bot.db.get_month_usage(run_time)
            cost_summary = pricing.build_cost_summary(usage_rows, run_time)
            report = build_report(results, run_time, cost_summary=cost_summary)
            chunks = [report[i:i+1900] for i in range(0, len(report), 1900)] or ["(empty report)"]
            for chunk in chunks:
                await interaction.user.send(chunk)
            await interaction.followup.send("Report sent to DM.", ephemeral=True)
        except Exception as e:
            await editor.update(f"❌ Classification error: {e}", force=True)
            await interaction.followup.send(f"Error: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RunCog(bot))

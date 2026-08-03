# bot/commands/reclassify.py
import os
from datetime import date, datetime, timedelta, UTC

import discord
from discord import app_commands
from discord.ext import commands

from peribot.core import pricing
from peribot.mail.classifier import classify, classify_by_rules, UNCLASSIFIED
from peribot.mail.fetcher import fetch_message, list_message_ids
from peribot.mail.labeler import ensure_label_exists, perimail_label_ids, replace_label
from peribot.mail.services import gmail_service_for_account

UNCLASSIFIED_LABEL = "PeriMail/Unclassified"


def _authorized(interaction: discord.Interaction) -> bool:
    return interaction.user.id == int(os.environ["DISCORD_USER_ID"])


def deeprun_since(today: date, months: int = 6) -> str:
    """Approximate window start (30 days/month) as a Gmail YYYY/MM/DD date string."""
    start = today - timedelta(days=30 * months)
    return start.strftime("%Y/%m/%d")


def _build_label_map(service, categories):
    label_ids = {c.name: ensure_label_exists(service, c.label) for c in categories}
    label_ids[UNCLASSIFIED] = ensure_label_exists(service, UNCLASSIFIED_LABEL)
    return label_ids


class ReclassifyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="reclassify-unclassified", description="Re-classify all previously unclassified emails")
    async def reclassify_unclassified(self, interaction: discord.Interaction):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return
        await interaction.response.send_message("Reclassifying unclassified emails…", ephemeral=True)
        db = self.bot.db
        moved = 0
        try:
            for account in await db.list_accounts():
                rows = await db.list_unclassified(account.email)
                if not rows:
                    continue
                service = gmail_service_for_account(account, self.bot.encryption_key)
                categories = await db.get_categories(account.account_type)
                label_ids = _build_label_map(service, categories)
                all_ids = perimail_label_ids(service) | set(label_ids.values())
                for row in rows:
                    try:
                        email = fetch_message(service, row["message_id"])
                    except Exception:
                        continue
                    category, method, usage = classify(email, categories, os.environ["GEMINI_API_KEY"])
                    if usage and (usage.input_tokens or usage.output_tokens):
                        await db.record_usage(pricing.MODEL, "classify", usage.input_tokens, usage.output_tokens)
                    if category != UNCLASSIFIED and category in label_ids:
                        replace_label(service, email.id, label_ids[category], all_ids)
                        await db.update_processed_category(email.id, account.email, category, method)
                        moved += 1
            await interaction.followup.send(f"Done. Moved {moved} emails out of Unclassified.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @app_commands.command(name="deeprun", description="Rules-only reclassify all emails in a window (default 6 months)")
    @app_commands.describe(months="How many months back to scan (default 6)")
    async def deeprun(self, interaction: discord.Interaction, months: int = 6):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return
        await interaction.response.send_message(f"Deep run started ({months} months, rules only)…", ephemeral=True)
        status = await interaction.user.send(f"🔍 Deep run: 0 processed…")
        db = self.bot.db
        since = deeprun_since(datetime.now(UTC).date(), months)
        processed = 0
        changed = 0
        try:
            for account in await db.list_accounts():
                service = gmail_service_for_account(account, self.bot.encryption_key)
                categories = await db.get_categories(account.account_type)
                label_ids = _build_label_map(service, categories)
                all_ids = perimail_label_ids(service) | set(label_ids.values())
                message_ids = list_message_ids(service, f"after:{since}")
                for mid in message_ids:
                    try:
                        email = fetch_message(service, mid)
                    except Exception:
                        continue
                    category = classify_by_rules(email, categories) or UNCLASSIFIED
                    target_label = label_ids.get(category, label_ids[UNCLASSIFIED])
                    replace_label(service, mid, target_label, all_ids)
                    await db.mark_processed(mid, account.email, category, "deeprun", subject=email.subject)
                    processed += 1
                    if category != UNCLASSIFIED:
                        changed += 1
                    if processed % 200 == 0:
                        try:
                            await status.edit(content=f"🔍 Deep run: {processed} processed…")
                        except Exception:
                            pass
            await status.edit(content=f"✅ Deep run done: {processed} processed, {changed} matched a category.")
        except Exception as e:
            await status.edit(content=f"❌ Deep run error after {processed}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ReclassifyCog(bot))

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

        if interaction.channel is None:
            await interaction.response.send_message("This command must be used in a server channel.", ephemeral=True)
            return

        channel = interaction.channel
        user_id = interaction.user.id

        def check(m: discord.Message) -> bool:
            return m.author.id == user_id and m.channel.id == channel.id

        async def ask(prompt: str) -> str:
            await channel.send(prompt)
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=60.0)
                try:
                    await msg.delete()
                except discord.Forbidden:
                    pass
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

        if interaction.channel is None:
            await interaction.response.send_message("This command must be used in a server channel.", ephemeral=True)
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
            try:
                await msg.delete()
            except discord.Forbidden:
                pass
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

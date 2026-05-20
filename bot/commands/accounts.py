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

        if interaction.channel is None:
            await interaction.response.send_message("This command must be used in a server channel.", ephemeral=True)
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
            try:
                await msg.delete()
            except discord.Forbidden:
                pass
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

        if interaction.channel is None:
            await interaction.response.send_message("This command must be used in a server channel.", ephemeral=True)
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
            try:
                await msg.delete()
            except discord.Forbidden:
                pass
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

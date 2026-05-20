# bot/commands/calendar.py
import os
from datetime import date, datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from perimail.auth import get_credentials
from perimail.calendar import (
    CalendarEvent, get_calendar_service, list_events, create_event,
    update_event, delete_event, find_events, get_event,
)
from perimail.crypto import decrypt
from perimail.report import _MONTH_NAMES


def _authorized(interaction: discord.Interaction) -> bool:
    return interaction.user.id == int(os.environ["DISCORD_USER_ID"])


def _parse_date(date_str: str) -> date:
    day, month = map(int, date_str.strip().split("/"))
    return date(datetime.now().year, month, day)


def _parse_datetime(date_str: str, time_str: str) -> datetime:
    d = _parse_date(date_str)
    h, m = map(int, time_str.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)


def _format_event(event: CalendarEvent) -> str:
    time_str = "All day" if event.all_day else event.start.strftime("%H:%M")
    location = f" @ {event.location}" if event.location else ""
    return f"  {time_str}  {event.title}{location} `({event.id})`"


class ConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.confirmed = False

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class CalendarCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_cal_service(self, email: str):
        account = await self.bot.db.get_account(email)
        if account is None:
            raise ValueError(f"Account `{email}` not found.")
        credentials = get_credentials(decrypt(account.encrypted_tokens, self.bot.encryption_key))
        return get_calendar_service(credentials)

    async def _resolve_email(self, interaction: discord.Interaction, account: Optional[str]) -> Optional[str]:
        if account:
            return account
        default = await self.bot.db.get_default_calendar(str(interaction.user.id))
        if default:
            return default
        await interaction.followup.send(
            "No default calendar set — use `/set-default-calendar` or pass `account`.",
            ephemeral=True,
        )
        return None

    @app_commands.command(name="events", description="List calendar events for a day")
    @app_commands.describe(
        date="Date in DD/MM format (default: today)",
        query="Search text (optional — filters by keyword)",
    )
    async def events(
        self,
        interaction: discord.Interaction,
        date: Optional[str] = None,
        query: Optional[str] = None,
    ):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            target = _parse_date(date) if date else datetime.now(timezone.utc).date()
        except ValueError:
            await interaction.followup.send("Invalid date format. Use DD/MM (e.g. 20/06).", ephemeral=True)
            return

        accounts = await self.bot.db.list_accounts()
        if not accounts:
            await interaction.followup.send("No accounts registered.", ephemeral=True)
            return

        date_str = f"{target.day} {_MONTH_NAMES[target.month - 1]}"
        lines = [f"**Calendar — {date_str}**", ""]

        for account in accounts:
            lines.append(f"**{account.email}**")
            try:
                service = await self._get_cal_service(account.email)
                if query:
                    account_events = find_events(service, query, target)
                else:
                    account_events = list_events(service, target)
                if not account_events:
                    lines.append("  No events")
                else:
                    for event in account_events:
                        lines.append(_format_event(event))
            except Exception as e:
                lines.append(f"  Error: {e} — run `/reauth-account` if calendar access is missing")
            lines.append("")

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="event-create", description="Create a calendar event")
    @app_commands.describe(
        title="Event title",
        date="Date in DD/MM format",
        start="Start time in HH:MM (UTC)",
        end="End time in HH:MM (UTC)",
        description="Event description (optional)",
        account="Account email (optional, uses default)",
    )
    async def event_create(
        self,
        interaction: discord.Interaction,
        title: str,
        date: str,
        start: str,
        end: str,
        description: Optional[str] = None,
        account: Optional[str] = None,
    ):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        email = await self._resolve_email(interaction, account)
        if not email:
            return

        try:
            start_dt = _parse_datetime(date, start)
            end_dt = _parse_datetime(date, end)
            service = await self._get_cal_service(email)
            event = create_event(service, "primary", title, start_dt, end_dt, description)
            await interaction.followup.send(
                f"Event created on `{email}`:\n{_format_event(event)}", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @app_commands.command(name="event-edit", description="Edit a calendar event")
    @app_commands.describe(
        event_id="Event ID shown in /events output",
        title="New title (optional)",
        date="New date in DD/MM (optional)",
        start="New start time in HH:MM UTC (optional)",
        end="New end time in HH:MM UTC (optional)",
        description="New description (optional)",
        account="Account email (optional, uses default)",
    )
    async def event_edit(
        self,
        interaction: discord.Interaction,
        event_id: str,
        title: Optional[str] = None,
        date: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        description: Optional[str] = None,
        account: Optional[str] = None,
    ):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        email = await self._resolve_email(interaction, account)
        if not email:
            return

        try:
            service = await self._get_cal_service(email)
            existing = get_event(service, event_id)
            if not existing:
                await interaction.followup.send(f"Event `{event_id}` not found on `{email}`.", ephemeral=True)
                return

            fields = {}
            if title:
                fields["title"] = title
            if description:
                fields["description"] = description
            if date and start:
                fields["start"] = _parse_datetime(date, start)
            elif start:
                fields["start"] = _parse_datetime(existing.start.strftime("%d/%m"), start)
            elif date:
                fields["start"] = _parse_datetime(date, existing.start.strftime("%H:%M"))

            if date and end:
                fields["end"] = _parse_datetime(date, end)
            elif end:
                fields["end"] = _parse_datetime(existing.end.strftime("%d/%m"), end)
            elif date:
                fields["end"] = _parse_datetime(date, existing.end.strftime("%H:%M"))

            if not fields:
                await interaction.followup.send("No fields to update were provided.", ephemeral=True)
                return

            event = update_event(service, event_id, existing.calendar_id, **fields)
            await interaction.followup.send(
                f"Event updated on `{email}`:\n{_format_event(event)}", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @app_commands.command(name="event-delete", description="Delete a calendar event")
    @app_commands.describe(
        event_id="Event ID shown in /events output",
        account="Account email (optional, uses default)",
    )
    async def event_delete(
        self,
        interaction: discord.Interaction,
        event_id: str,
        account: Optional[str] = None,
    ):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        email = await self._resolve_email(interaction, account)
        if not email:
            return

        try:
            service = await self._get_cal_service(email)
            existing = get_event(service, event_id)
            if not existing:
                await interaction.followup.send(f"Event `{event_id}` not found on `{email}`.", ephemeral=True)
                return

            view = ConfirmView()
            await interaction.followup.send(
                f"Delete **{existing.title}** from `{email}`?",
                view=view,
                ephemeral=True,
            )
            await view.wait()

            if view.confirmed:
                delete_event(service, event_id, existing.calendar_id)
                await interaction.followup.send(f"Event **{existing.title}** deleted.", ephemeral=True)
            else:
                await interaction.followup.send("Cancelled.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @app_commands.command(name="set-default-calendar", description="Set default account for calendar commands")
    @app_commands.describe(email="Account email to use as default")
    async def set_default_calendar(self, interaction: discord.Interaction, email: str):
        if not _authorized(interaction):
            await interaction.response.send_message("Unauthorized.", ephemeral=True)
            return

        accounts = await self.bot.db.list_accounts()
        if not any(a.email == email for a in accounts):
            await interaction.response.send_message(
                f"`{email}` not found in registered accounts.", ephemeral=True
            )
            return

        await self.bot.db.set_default_calendar(str(interaction.user.id), email)
        await interaction.response.send_message(f"Default calendar set to `{email}`.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CalendarCog(bot))

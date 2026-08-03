# bot/commands/proposals.py
import os
from collections import defaultdict

import discord
from discord.ext import commands, tasks

from peribot.mail.db import Proposal
from peribot.mail.labeler import ensure_label_exists, perimail_label_ids, replace_label
from peribot.mail.services import gmail_service_for_account


def format_proposal_text(proposal: Proposal) -> str:
    lines = [f"**Proposed category: {proposal.name}**", proposal.description, ""]
    if proposal.keywords:
        lines.append("Keywords: " + ", ".join(proposal.keywords))
    if proposal.samples:
        lines.append("Sample emails:")
        for s in proposal.samples[:5]:
            lines.append(f"  • {s['subject']}")
    return "\n".join(lines)


class ProposalView(discord.ui.View):
    def __init__(self, cog: "ProposalsCog", proposal_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.proposal_id = proposal_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            name = await self.cog.approve_proposal(self.proposal_id)
            await interaction.message.edit(content=f"✅ Approved category **{name}**.", view=None)
        except Exception as e:
            await interaction.followup.send(f"Approve failed: {e}", ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.bot.db.set_proposal_status(self.proposal_id, "rejected")
        await interaction.message.edit(content="❌ Proposal rejected.", view=None)


class ProposalsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poll_proposals.start()

    def cog_unload(self):
        self.poll_proposals.cancel()

    async def approve_proposal(self, proposal_id: int) -> str:
        db = self.bot.db
        p = await db.get_proposal(proposal_id)
        if p is None or p.status != "pending":
            raise ValueError("proposal not pending")
        label = f"PeriMail/{p.name}"
        await db.add_category(p.name, label, p.description, p.keywords, [], "all")

        by_account = defaultdict(list)
        for s in p.samples:
            by_account[s["account_email"]].append(s["message_id"])

        for email, message_ids in by_account.items():
            account = await db.get_account(email)
            if account is None:
                continue
            service = gmail_service_for_account(account, self.bot.encryption_key)
            new_label_id = ensure_label_exists(service, label)
            existing_ids = perimail_label_ids(service) | {new_label_id}
            for mid in message_ids:
                replace_label(service, mid, new_label_id, existing_ids)
                await db.update_processed_category(mid, email, p.name, "approved")

        await db.set_proposal_status(proposal_id, "approved")
        return p.name

    @tasks.loop(seconds=60)
    async def poll_proposals(self):
        try:
            pending = await self.bot.db.list_pending_proposals_without_message()
        except Exception as e:
            print(f"poll_proposals: DB error: {e}")
            return
        if not pending:
            return
        try:
            user = await self.bot.fetch_user(int(os.environ["DISCORD_USER_ID"]))
        except Exception as e:
            print(f"poll_proposals: cannot fetch user: {e}")
            return
        for p in pending:
            try:
                view = ProposalView(self, p.id)
                msg = await user.send(format_proposal_text(p), view=view)
                await self.bot.db.mark_proposal_posted(p.id, str(msg.id))
            except Exception as e:
                print(f"poll_proposals: failed to post proposal {p.id}: {e}")

    @poll_proposals.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(ProposalsCog(bot))

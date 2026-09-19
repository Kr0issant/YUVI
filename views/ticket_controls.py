import os
import asyncio
import discord
from discord import ui
from typing import Optional

from models.ticket import TicketStatus, TicketUser
from utils.ticket_manager import TicketManager
from utils.transcript_generator import TranscriptGenerator

class CloseReasonModal(ui.Modal, title="🔒 Close Ticket"):
    reason = ui.TextInput(
        label="Closing Reason / Resolution Notes",
        placeholder="e.g., SPG registered successfully / Issue resolved / Requested info provided",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False
    )

    def __init__(self, ticket_id: str):
        super().__init__()
        self.ticket_id = ticket_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        ticket = await TicketManager.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.followup.send("❌ Ticket record not found in database.", ephemeral=True)
            return

        closing_user = TicketUser(
            discord_id=str(interaction.user.id),
            username=interaction.user.name,
            avatar_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None
        )

        close_reason = self.reason.value or "Closed by user/admin"
        await TicketManager.close_ticket(self.ticket_id, closing_user, close_reason)

        # Generate and post transcript
        messages = await TicketManager.get_ticket_messages(self.ticket_id)
        transcript_file = TranscriptGenerator.generate_text_transcript(ticket, messages)
        discord_file = discord.File(transcript_file, filename=f"transcript-{self.ticket_id}.txt")

        # Send closing notification embed in thread
        close_embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=f"This ticket has been closed by {interaction.user.mention}.\n**Reason:** {close_reason}",
            color=0xED4245 # Red
        )
        close_embed.set_footer(text=f"Ticket ID: {self.ticket_id} • Reinforce Club")

        # Send to transcript log channel if configured
        log_channel_id = os.getenv("TRANSCRIPTS_CHANNEL_ID")
        if log_channel_id and interaction.guild:
            try:
                log_channel = interaction.guild.get_channel(int(log_channel_id))
                if isinstance(log_channel, discord.TextChannel):
                    log_file = discord.File(
                        TranscriptGenerator.generate_text_transcript(ticket, messages),
                        filename=f"transcript-{self.ticket_id}.txt"
                    )
                    await log_channel.send(
                        content=f"📑 **Transcript Archive** | Ticket `{self.ticket_id}` ({ticket.category.label}) closed by {interaction.user.mention}",
                        file=log_file
                    )
            except Exception as e:
                print(f"Error posting to log channel: {e}")

        # Post close embed & transcript in thread
        if isinstance(interaction.channel, (discord.Thread, discord.TextChannel)):
            await interaction.channel.send(embed=close_embed, file=discord_file)
            await interaction.channel.send("⏳ *This thread will be archived and locked in 5 seconds...*")
            await asyncio.sleep(5)
            if isinstance(interaction.channel, discord.Thread):
                await interaction.channel.edit(archived=True, locked=True)


class AddMemberModal(ui.Modal, title="➕ Add Member to Ticket"):
    member_input = ui.TextInput(
        label="Member ID or @Mention",
        placeholder="e.g. 123456789012345678 or @username",
        max_length=50,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("❌ This command only works inside a ticket thread.", ephemeral=True)
            return

        raw = self.member_input.value.strip().replace("<@", "").replace(">", "").replace("!", "")
        if not raw.isdigit():
            await interaction.response.send_message("❌ Invalid user ID or mention provided.", ephemeral=True)
            return

        user_id = int(raw)
        guild = interaction.guild
        member = guild.get_member(user_id) if guild else None

        if not member:
            try:
                member = await guild.fetch_member(user_id)
            except Exception:
                member = None

        if not member:
            await interaction.response.send_message("❌ Member not found in this server.", ephemeral=True)
            return

        try:
            await interaction.channel.add_user(member)
            await interaction.response.send_message(f"✅ Added {member.mention} to this ticket thread.")
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to add member: {e}", ephemeral=True)


class TicketControlView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="Claim Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🙋‍♂️",
        custom_id="persistent_ticket_claim"
    )
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button):
        if not isinstance(interaction.channel, (discord.Thread, discord.TextChannel)):
            await interaction.response.send_message("❌ Action can only be performed in a ticket channel/thread.", ephemeral=True)
            return

        ticket = await TicketManager.get_ticket_by_thread_id(str(interaction.channel.id))
        if not ticket:
            await interaction.response.send_message("❌ Could not locate ticket metadata in database.", ephemeral=True)
            return

        if ticket.status == TicketStatus.CLOSED:
            await interaction.response.send_message("❌ This ticket is already closed.", ephemeral=True)
            return

        admin_user = TicketUser(
            discord_id=str(interaction.user.id),
            username=interaction.user.name,
            avatar_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None
        )

        await TicketManager.claim_ticket(ticket.id, admin_user)

        claim_embed = discord.Embed(
            description=f"🙋‍♂️ **Ticket Claimed!**\n{interaction.user.mention} is now handling this ticket.",
            color=0xFEE75C # Yellow
        )
        await interaction.response.send_message(embed=claim_embed)

    @ui.button(
        label="Add Member",
        style=discord.ButtonStyle.secondary,
        emoji="➕",
        custom_id="persistent_ticket_add_member"
    )
    async def add_member_button(self, interaction: discord.Interaction, button: ui.Button):
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("❌ Action can only be performed in a ticket thread.", ephemeral=True)
            return
        await interaction.response.send_modal(AddMemberModal())

    @ui.button(
        label="Transcript",
        style=discord.ButtonStyle.secondary,
        emoji="📑",
        custom_id="persistent_ticket_transcript"
    )
    async def transcript_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)

        ticket = await TicketManager.get_ticket_by_thread_id(str(interaction.channel.id))
        if not ticket:
            await interaction.followup.send("❌ Could not find ticket record.", ephemeral=True)
            return

        messages = await TicketManager.get_ticket_messages(ticket.id)
        transcript_file = TranscriptGenerator.generate_text_transcript(ticket, messages)
        discord_file = discord.File(transcript_file, filename=f"transcript-{ticket.id}.txt")

        await interaction.followup.send(
            content=f"📑 **Ticket Transcript** for `{ticket.id}` ({len(messages)} messages):",
            file=discord_file,
            ephemeral=True
        )

    @ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="persistent_ticket_close"
    )
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        ticket = await TicketManager.get_ticket_by_thread_id(str(interaction.channel.id))
        if not ticket:
            await interaction.response.send_message("❌ Could not find ticket in database.", ephemeral=True)
            return

        if ticket.status == TicketStatus.CLOSED:
            await interaction.response.send_message("❌ This ticket is already closed.", ephemeral=True)
            return

        await interaction.response.send_modal(CloseReasonModal(ticket.id))

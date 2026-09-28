import os
import discord
from discord import ui
from typing import Dict, Any, Optional

from models.ticket import (
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    TicketUser,
    DiscordMeta,
    TicketMessage
)
from utils.ticket_manager import TicketManager

async def create_ticket_thread_and_doc(
    interaction: discord.Interaction,
    category: TicketCategory,
    title: str,
    description: str,
    fields: Dict[str, Any]
):
    """Helper to create a private Discord thread and save the ticket to Firestore."""
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ This action must be performed in a Discord server.", ephemeral=True)
        return

    # Defer interaction response early to prevent timeout
    await interaction.response.defer(ephemeral=True, thinking=True)

    # Determine channel for thread creation (configured channel or interaction channel)
    configured_channel_id = os.getenv("TICKETS_CHANNEL_ID")
    target_channel = guild.get_channel(int(configured_channel_id)) if configured_channel_id else interaction.channel
    
    if not isinstance(target_channel, (discord.TextChannel, discord.ForumChannel)):
        target_channel = interaction.channel

    if not isinstance(target_channel, (discord.TextChannel, discord.ForumChannel)):
        await interaction.followup.send("❌ Tickets channel must be a text or forum channel.", ephemeral=True)
        return

    # Clean username for thread name
    clean_username = "".join(c for c in interaction.user.name.lower() if c.isalnum() or c in ("-", "_"))[:15]
    thread_name = f"{category.emoji}-{category.short_name}-{clean_username}"

    try:
        # Create private thread
        # discord.ChannelType.private_thread requires private thread permissions
        thread = await target_channel.create_thread(
            name=thread_name,
            auto_archive_duration=10080, # 7 days
            type=discord.ChannelType.private_thread,
            reason=f"Support Ticket for {interaction.user} ({category.value})"
        )
    except discord.Forbidden:
        # Fallback to public thread if private thread permission isn't available
        try:
            thread = await target_channel.create_thread(
                name=thread_name,
                auto_archive_duration=10080,
                reason=f"Support Ticket for {interaction.user} ({category.value})"
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to create ticket thread: {e}", ephemeral=True)
            return
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to create ticket thread: {e}", ephemeral=True)
        return

    # Add user to the thread
    try:
        await thread.add_user(interaction.user)
    except Exception:
        pass

    # Build Ticket model
    ticket_user = TicketUser(
        discord_id=str(interaction.user.id),
        username=interaction.user.name,
        discriminator=getattr(interaction.user, "discriminator", None),
        avatar_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None
    )

    discord_meta = DiscordMeta(
        guild_id=str(guild.id),
        channel_id=str(target_channel.id),
        thread_id=str(thread.id)
    )

    ticket = Ticket(
        category=category,
        title=title,
        description=description,
        fields=fields,
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
        created_by=ticket_user,
        discord_meta=discord_meta,
        thread_id=str(thread.id),
        guild_id=str(guild.id)
    )

    try:
        # Save to Firestore
        ticket_id = await TicketManager.create_ticket(ticket)
        ticket.id = ticket_id

        # Add initial creation message to the Firestore messages subcollection
        initial_msg = TicketMessage(
            sender_id=str(interaction.user.id),
            sender_name=interaction.user.name,
            sender_avatar=interaction.user.display_avatar.url if interaction.user.display_avatar else None,
            sender_role="user",
            source="discord",
            content=f"**[{category.label}] {title}**\n\n{description}"
        )
        await TicketManager.add_ticket_message(ticket_id, initial_msg)
    except Exception as e:
        print(f"[TicketCreation] Error saving ticket to Firestore: {e}")
        import traceback
        traceback.print_exc()
        await interaction.followup.send(f"⚠️ Thread created, but encountered a database error: {e}", ephemeral=True)
        ticket_id = str(thread.id)

    # Build rich embed for the ticket thread header
    embed = discord.Embed(
        title=f"{category.emoji} {title}",
        description=f"Welcome {interaction.user.mention}! Support team and track leads will assist you shortly.\n\nUse the buttons below to manage this ticket.",
        color=0x5865F2 # Discord Blurple / Reinforce Blue
    )
    embed.add_field(name="📋 Category", value=category.label, inline=True)
    embed.add_field(name="🆔 Ticket ID", value=f"`{ticket_id}`", inline=True)
    embed.add_field(name="🚦 Status", value="🟢 Open", inline=True)
    embed.add_field(name="👤 Opened By", value=interaction.user.mention, inline=True)
    embed.add_field(name="⏰ Priority", value="Medium", inline=True)
    
    # Add custom fields if any
    for k, v in fields.items():
        if v and len(str(v)) > 0:
            embed.add_field(name=f"📌 {k}", value=str(v)[:1024], inline=False)

    embed.set_footer(text="Reinforce Club Ticket System • Synced with Firestore Dashboard", icon_url=guild.icon.url if guild.icon else None)

    # Import controls view here to avoid circular imports
    from views.ticket_controls import TicketControlView
    control_view = TicketControlView()

    # Ping admin/support role if configured
    admin_role_id = os.getenv("ADMIN_ROLE_ID") or os.getenv("SUPPORT_ROLE_ID")
    admin_mention = f"<@&{admin_role_id}>" if admin_role_id else ""

    control_msg = await thread.send(
        content=f"{interaction.user.mention} {admin_mention}",
        embed=embed,
        view=control_view
    )

    # Update control message ID in Firestore
    await TicketManager.update_ticket(ticket_id, {
        "discord_meta.control_message_id": str(control_msg.id)
    })

    await interaction.followup.send(f"✅ Your ticket has been created: {thread.mention}", ephemeral=True)


class SPGModal(ui.Modal, title="🚀 SPG Registration / Modification"):
    project_name = ui.TextInput(
        label="Project Name & Track",
        placeholder="e.g., Project Phoenix (Research / Product / Kaggle / General)",
        max_length=100,
        required=True
    )
    team_leader = ui.TextInput(
        label="Team Leader Firebase UID",
        placeholder="Mandatory Firebase UID of team leader (must be club member)",
        max_length=128,
        required=True
    )
    team_members = ui.TextInput(
        label="Team Member UIDs (Optional, max 6)",
        placeholder="One Firebase UID per line (newline-separated, up to 6 members)",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=False
    )
    duration = ui.TextInput(
        label="Estimated Duration (in days)",
        placeholder="e.g. 60 (integer number of days)",
        max_length=10,
        required=True
    )
    frequency = ui.TextInput(
        label="Report Frequency (in days)",
        placeholder="e.g. 14 (integer number of days between reports)",
        max_length=10,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        leader_uid = self.team_leader.value.strip()
        if "(" in leader_uid and leader_uid.endswith(")"):
            leader_uid = leader_uid.split("(")[-1].rstrip(")")

        member_uids = [
            line.strip()
            for line in self.team_members.value.splitlines()
            if line.strip() and line.strip().lower() != "none"
        ]
        # Clean any appended names or parentheses if provided
        cleaned_members = []
        for m in member_uids:
            if "(" in m and m.endswith(")"):
                m = m.split("(")[-1].rstrip(")")
            if m and m != leader_uid and m not in cleaned_members:
                cleaned_members.append(m)

        if len(cleaned_members) > 6:
            await interaction.followup.send("❌ Maximum 6 team members allowed (excluding team leader).", ephemeral=True)
            return

        try:
            duration_days = int(self.duration.value.strip())
            frequency_days = int(self.frequency.value.strip())
            if duration_days <= 0 or frequency_days <= 0:
                raise ValueError()
        except ValueError:
            await interaction.followup.send("❌ Duration and report frequency must be positive integers (days).", ephemeral=True)
            return

        fields = {
            "project_name": self.project_name.value.strip(),
            "leader_uid": leader_uid,
            "member_uids": cleaned_members,
            "duration_days": duration_days,
            "frequency_days": frequency_days,
            "Team Leader": leader_uid,
            "Team Members": ", ".join(cleaned_members) if cleaned_members else "None",
            "Duration (Days)": duration_days,
            "Report Frequency (Days)": frequency_days,
        }
        await create_ticket_thread_and_doc(
            interaction=interaction,
            category=TicketCategory.SPG_REGISTRATION,
            title=f"SPG: {self.project_name.value.strip()}",
            description=f"Project Group: {self.project_name.value.strip()} | Leader: {leader_uid} | Duration: {duration_days} days | Frequency: every {frequency_days} days",
            fields=fields
        )


class ComputeResourceRequestModal(ui.Modal, title="⚡ Compute Resource Request (SPGs Only)"):
    project_name = ui.TextInput(
        label="Registered SPG Project Name",
        placeholder="e.g., Project Phoenix",
        max_length=100,
        required=True
    )
    resources_needed = ui.TextInput(
        label="Resources Required",
        placeholder="e.g., Kaggle GPU / Cloud Compute / API Credits / Hardware / Mentorship",
        max_length=200,
        required=True
    )
    progress_proof = ui.TextInput(
        label="Proof of Existing Progress & Links",
        placeholder="GitHub repo link, demo URL, research draft, or past milestone report...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    justification = ui.TextInput(
        label="Purpose & Resource Justification",
        placeholder="Why are these resources needed and how will they accelerate your milestones?",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        fields = {
            "SPG Name": self.project_name.value,
            "Resources Requested": self.resources_needed.value,
            "Progress Proof": self.progress_proof.value,
            "Justification": self.justification.value,
            "project_name": self.project_name.value,
            "resources_needed": self.resources_needed.value,
            "progress_proof_url": self.progress_proof.value,
        }
        await create_ticket_thread_and_doc(
            interaction=interaction,
            category=TicketCategory.COMPUTE_RESOURCE_REQUEST,
            title=f"Compute Resource Request: {self.project_name.value}",
            description=self.justification.value,
            fields=fields
        )


ResourceRequestModal = ComputeResourceRequestModal


class LearningResourceRequestModal(ui.Modal, title="📚 Learning Resource Request"):
    topic = ui.TextInput(
        label="Topic / Subject Area",
        placeholder="e.g., Transformer Architectures / Diffusion Models / Web Dev",
        max_length=100,
        required=True
    )
    resource_format = ui.TextInput(
        label="Resource Format",
        placeholder="e.g., Curated Roadmap / Video Course / Research Papers / Book Guide",
        max_length=100,
        required=True
    )
    target_audience = ui.TextInput(
        label="Target Audience / Track",
        placeholder="e.g., Research Track (Beginners) / Kaggle Competitors",
        max_length=100,
        required=True
    )
    description = ui.TextInput(
        label="Description & Suggested Links",
        placeholder="What should be included, suggested URLs or curriculum details...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        fields = {
            "Topic / Subject Area": self.topic.value,
            "Resource Format": self.resource_format.value,
            "Target Audience / Track": self.target_audience.value,
            "Description & Suggested Links": self.description.value,
            "topic": self.topic.value,
            "resource_format": self.resource_format.value,
        }
        await create_ticket_thread_and_doc(
            interaction=interaction,
            category=TicketCategory.LEARNING_RESOURCE_REQUEST,
            title=f"Learning Resource: {self.topic.value}",
            description=self.description.value,
            fields=fields
        )


class SupportInquiryModal(ui.Modal, title="💬 Support & General Inquiries"):
    subject = ui.TextInput(
        label="Subject / Topic",
        placeholder="e.g., Question about upcoming Kaggle Datathon",
        max_length=100,
        required=True
    )
    details = ui.TextInput(
        label="Details & Question",
        placeholder="Explain what you need assistance with...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        fields = {
            "subject": self.subject.value,
            "details": self.details.value
        }
        await create_ticket_thread_and_doc(
            interaction=interaction,
            category=TicketCategory.SUPPORT,
            title=self.subject.value,
            description=self.details.value,
            fields=fields
        )


class IdeaJarModal(ui.Modal, title="💡 Idea Jar & Suggestions"):
    idea_title = ui.TextInput(
        label="Idea / Suggestion Title",
        placeholder="e.g., Automated Kaggle Notebook Benchmark Bot",
        max_length=100,
        required=True
    )
    track = ui.TextInput(
        label="Target Track / Category",
        placeholder="e.g., Product / Kaggle / Research / Club Events",
        max_length=100,
        required=True
    )
    overview = ui.TextInput(
        label="Idea Description & Learning Objectives",
        placeholder="What is the concept, skill requirements, and learning objectives for someone building this?",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        fields = {
            "idea_title": self.idea_title.value,
            "track": self.track.value,
            "overview": self.overview.value
        }
        await create_ticket_thread_and_doc(
            interaction=interaction,
            category=TicketCategory.IDEA_JAR,
            title=f"Idea Jar: {self.idea_title.value}",
            description=self.overview.value,
            fields=fields
        )


class FeedbackModal(ui.Modal, title="📝 Feedback & Suggestions"):
    topic = ui.TextInput(
        label="Feedback Topic",
        placeholder="e.g., Workshop pacing, Discord channels, Website UX",
        max_length=100,
        required=True
    )
    comments = ui.TextInput(
        label="Feedback & Details",
        placeholder="Share what worked well and what we can improve...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        fields = {
            "topic": self.topic.value,
            "comments": self.comments.value
        }
        await create_ticket_thread_and_doc(
            interaction=interaction,
            category=TicketCategory.FEEDBACK,
            title=f"Feedback: {self.topic.value}",
            description=self.comments.value,
            fields=fields
        )


class ReportModal(ui.Modal, title="🛡️ Report Issue / Misconduct (Confidential)"):
    summary = ui.TextInput(
        label="Incident Summary",
        placeholder="Brief summary of the issue or concern",
        max_length=100,
        required=True
    )
    description = ui.TextInput(
        label="Detailed Report",
        placeholder="Provide all relevant details, names, dates, or context. This is visible only to core admins.",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        fields = {
            "incident_summary": self.summary.value,
            "confidential_details": self.description.value
        }
        await create_ticket_thread_and_doc(
            interaction=interaction,
            category=TicketCategory.REPORT,
            title=f"Report: {self.summary.value}",
            description=self.description.value,
            fields=fields
        )


class MiscModal(ui.Modal, title="📦 General Ticket"):
    subject = ui.TextInput(
        label="Subject",
        placeholder="Brief subject of your ticket",
        max_length=100,
        required=True
    )
    details = ui.TextInput(
        label="Description",
        placeholder="Please describe your request...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        fields = {
            "subject": self.subject.value,
            "details": self.details.value
        }
        await create_ticket_thread_and_doc(
            interaction=interaction,
            category=TicketCategory.MISC,
            title=self.subject.value,
            description=self.details.value,
            fields=fields
        )

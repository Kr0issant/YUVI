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
        label="Project Name",
        placeholder="e.g., Project Phoenix",
        max_length=100,
        required=True
    )
    track = ui.TextInput(
        label="Track",
        placeholder="Research / Product / Kaggle / General",
        max_length=50,
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
    duration_and_frequency = ui.TextInput(
        label="Duration & Frequency in days (e.g. 60, 14)",
        placeholder="e.g., 60, 14 (total days, days between reports)",
        max_length=50,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        import re

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

        parts = [p.strip() for p in re.split(r'[,/;\s]+', self.duration_and_frequency.value.strip()) if p.strip()]
        try:
            if not parts:
                raise ValueError()
            duration_days = int(parts[0])
            frequency_days = int(parts[1]) if len(parts) > 1 else 14
            if duration_days <= 0 or frequency_days <= 0:
                raise ValueError()
        except (ValueError, IndexError):
            await interaction.followup.send("❌ Please enter duration and frequency as positive numbers in days (e.g. 60, 14).", ephemeral=True)
            return

        track_clean = self.track.value.strip()
        fields = {
            "project_name": self.project_name.value.strip(),
            "track": track_clean,
            "leader_uid": leader_uid,
            "member_uids": cleaned_members,
            "duration_days": duration_days,
            "frequency_days": frequency_days,
            "Project Name": self.project_name.value.strip(),
            "Track": track_clean,
            "Team Leader": leader_uid,
            "Team Members": ", ".join(cleaned_members) if cleaned_members else "None",
            "Duration (Days)": duration_days,
            "Report Frequency (Days)": frequency_days,
        }
        await create_ticket_thread_and_doc(
            interaction=interaction,
            category=TicketCategory.SPG_REGISTRATION,
            title=f"SPG: {self.project_name.value.strip()} ({track_clean})",
            description=f"Project Group: {self.project_name.value.strip()} | Track: {track_clean} | Leader: {leader_uid} | Duration: {duration_days} days | Frequency: every {frequency_days} days",
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


class IdeaJarModal(ui.Modal, title="💡 Idea Jar Proposal"):
    idea_title = ui.TextInput(
        label="Idea Title & Track / Difficulty",
        placeholder="e.g., Autonomous Agents Platform (Research / Intermediate)",
        max_length=150,
        required=True
    )
    overview = ui.TextInput(
        label="Overview & Problem Statement",
        placeholder="What problem does this solve, and what is the technical approach?",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )
    prerequisites = ui.TextInput(
        label="Prerequisites (1 per line)",
        placeholder="e.g.,\nPython\nPyTorch basics\nTransformers library",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=False
    )
    roadmap = ui.TextInput(
        label="Rough Roadmap (1 step per line)",
        placeholder="e.g.,\nPhase 1: Literature review\nPhase 2: Baseline architecture\nPhase 3: Benchmarks",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=False
    )
    learning_outcomes = ui.TextInput(
        label="Learning Outcomes (1 per line)",
        placeholder="e.g.,\nHands-on distributed training\nBenchmarking pipelines\nPaper preprint",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        import re
        raw_title = self.idea_title.value.strip()
        track = "General"
        difficulty = "Intermediate"
        clean_title = raw_title

        match = re.search(r'[\(|\[](.*?)[\)|\]]$', raw_title)
        if match:
            meta_str = match.group(1)
            clean_title = raw_title[:match.start()].strip()
            parts = [p.strip() for p in re.split(r'[/,;|]+', meta_str) if p.strip()]
            if len(parts) >= 1:
                track = parts[0]
            if len(parts) >= 2:
                difficulty = parts[1]
        elif "|" in raw_title:
            parts = [p.strip() for p in raw_title.split("|")]
            clean_title = parts[0].strip()
            if len(parts) >= 2:
                track = parts[1].strip()
            if len(parts) >= 3:
                difficulty = parts[2].strip()

        prereqs_list = [line.strip().lstrip("-*•0123456789. ") for line in self.prerequisites.value.splitlines() if line.strip()]
        roadmap_list = [line.strip().lstrip("-*•0123456789. ") for line in self.roadmap.value.splitlines() if line.strip()]
        outcomes_list = [line.strip().lstrip("-*•0123456789. ") for line in self.learning_outcomes.value.splitlines() if line.strip()]

        fields = {
            "Idea Title": clean_title,
            "Track": track,
            "Difficulty": difficulty,
            "Overview": self.overview.value.strip(),
            "Prerequisites": "\n".join(f"• {p}" for p in prereqs_list) if prereqs_list else "None specified",
            "Rough Roadmap": "\n".join(f"{i+1}. {r}" for i, r in enumerate(roadmap_list)) if roadmap_list else "None specified",
            "Learning Outcomes": "\n".join(f"• {o}" for o in outcomes_list) if outcomes_list else "None specified",
            "idea_title": clean_title,
            "track": track.lower(),
            "difficulty": difficulty.lower() if difficulty else None,
            "overview": self.overview.value.strip(),
            "description": self.overview.value.strip(),
            "prerequisites": prereqs_list,
            "rough_roadmap": roadmap_list,
            "learning_outcomes": outcomes_list,
        }
        await create_ticket_thread_and_doc(
            interaction=interaction,
            category=TicketCategory.IDEA_JAR,
            title=f"Idea Jar: {clean_title}",
            description=f"**Track:** {track} | **Difficulty:** {difficulty}\n\n{self.overview.value.strip()}",
            fields=fields
        )


class FeedbackModal(ui.Modal, title="📝 Suggestions & Feedback"):
    topic = ui.TextInput(
        label="Suggestion / Feedback Topic",
        placeholder="e.g., Workshop pacing, Discord structure, Website UX, New events",
        max_length=100,
        required=True
    )
    comments = ui.TextInput(
        label="Suggestions & Details",
        placeholder="Share your suggestions, recommendations, or feedback in detail...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        fields = {
            "Suggestion Topic": self.topic.value.strip(),
            "Details": self.comments.value.strip(),
            "topic": self.topic.value.strip(),
            "comments": self.comments.value.strip()
        }
        await create_ticket_thread_and_doc(
            interaction=interaction,
            category=TicketCategory.FEEDBACK,
            title=f"Suggestion: {self.topic.value.strip()}",
            description=self.comments.value.strip(),
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

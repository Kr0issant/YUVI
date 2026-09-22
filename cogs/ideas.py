import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal

from models.idea import Idea, IdeaTrack, IdeaDifficulty
from models.ticket import TicketUser
from utils.idea_manager import IdeaManager
from views.idea_views import (
    IdeaPanelView,
    RandomIdeaRerollView,
    build_idea_embed
)

class IdeasCog(commands.Cog, name="IdeaJar"):
    """Idea Jar system for Reinforce Club project ideas and SPGs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Register persistent view so panel buttons work across bot restarts
        self.bot.add_view(IdeaPanelView())

    idea_group = app_commands.Group(name="idea", description="Idea Jar project commands")

    @app_commands.command(name="setup-ideajar", description="Deploy the interactive Idea Jar panel")
    @app_commands.describe(channel="Channel to post the Idea Jar panel into (defaults to current channel)")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_ideajar(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None
    ):
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message("❌ Target must be a text channel.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🏺 Reinforce Club — Idea Jar",
            description=(
                "Welcome to the **Reinforce Idea Jar**!\n\n"
                "Looking for a project to build for your Student Project Group (SPG), Kaggle competition, or research track? "
                "Draw an idea from the jar or submit your own concept for community building.\n\n"
                "• **🎲 Get Random Idea**: Draws an approved project idea with learning outcomes & roadmap.\n"
                "• **💡 Submit an Idea**: Submit a project concept for review by the track leads."
            ),
            color=0x5865F2 # Reinforce Blurple
        )
        embed.set_footer(text="Reinforce Club SST • Project Incubator")
        if interaction.guild and interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        await target_channel.send(embed=embed, view=IdeaPanelView())
        await interaction.response.send_message(f"✅ Idea Jar panel deployed to {target_channel.mention}!", ephemeral=True)

    @idea_group.command(name="get", description="Fetch details of a specific idea by its ID")
    @app_commands.describe(idea_id="The unique ID of the idea")
    async def idea_get(self, interaction: discord.Interaction, idea_id: str):
        await interaction.response.defer(ephemeral=False)

        idea = await IdeaManager.get_idea(idea_id)
        if not idea:
            await interaction.followup.send(f"❌ Idea with ID `{idea_id}` not found.")
            return

        embed = build_idea_embed(idea)
        if not idea.is_approved:
            embed.add_field(name="Approval Status", value="⏳ Pending Admin Approval", inline=False)

        await interaction.followup.send(embed=embed)

    @idea_group.command(name="random", description="Draw a random approved project idea from the Idea Jar")
    @app_commands.describe(
        track="Filter by project track",
        difficulty="Filter by difficulty level"
    )
    async def idea_random(
        self,
        interaction: discord.Interaction,
        track: Optional[Literal["research", "product", "kaggle", "other"]] = None,
        difficulty: Optional[Literal["beginner", "intermediate", "advanced"]] = None
    ):
        await interaction.response.defer(ephemeral=True)

        idea = await IdeaManager.get_random_idea(track=track, difficulty=difficulty)
        if not idea:
            await interaction.followup.send(
                "No approved ideas found matching your selected filters.",
                ephemeral=True
            )
            return

        embed = build_idea_embed(idea)
        view = RandomIdeaRerollView(track=track, difficulty=difficulty)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @idea_group.command(name="list", description="List ideas from the Idea Jar")
    @app_commands.describe(
        track="Filter by project track",
        status="Filter by approval status"
    )
    async def idea_list(
        self,
        interaction: discord.Interaction,
        track: Optional[Literal["research", "product", "kaggle", "other"]] = None,
        status: Optional[Literal["approved", "pending", "all"]] = "approved"
    ):
        await interaction.response.defer(ephemeral=True)

        is_approved_filter = None
        if status == "approved":
            is_approved_filter = True
        elif status == "pending":
            is_approved_filter = False

        ideas = await IdeaManager.list_ideas(is_approved=is_approved_filter, track=track, limit=20)
        if not ideas:
            await interaction.followup.send("No ideas found matching criteria.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🏺 Reinforce Idea Jar ({len(ideas)} Ideas)",
            color=0xFEE75C
        )

        for idea in ideas:
            status_tag = "✅" if idea.is_approved else "⏳ Pending"
            embed.add_field(
                name=f"{idea.title} [`{idea.id}`]",
                value=f"**Track:** {idea.track.capitalize()} | **Difficulty:** {idea.difficulty.capitalize()} | **Status:** {status_tag}\n{idea.description[:120]}...",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @idea_group.command(name="approve", description="Approve a submitted project idea")
    @app_commands.describe(idea_id="The unique ID of the idea to approve")
    @app_commands.checks.has_permissions(administrator=True)
    async def idea_approve(self, interaction: discord.Interaction, idea_id: str):
        await interaction.response.defer(ephemeral=True)

        admin_user = TicketUser(
            discord_id=str(interaction.user.id),
            username=interaction.user.name,
            avatar_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None
        )

        success = await IdeaManager.approve_idea(idea_id, admin_user)
        if success:
            idea = await IdeaManager.get_idea(idea_id)
            await interaction.followup.send(f"✅ Idea `{idea_id}` ({idea.title if idea else ''}) has been approved and added to the Idea Jar!", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Failed to approve idea `{idea_id}` (ID not found).", ephemeral=True)

    @idea_group.command(name="delete", description="Delete an idea from the Idea Jar")
    @app_commands.describe(idea_id="The unique ID of the idea to delete")
    @app_commands.checks.has_permissions(administrator=True)
    async def idea_delete(self, interaction: discord.Interaction, idea_id: str):
        await interaction.response.defer(ephemeral=True)

        success = await IdeaManager.delete_idea(idea_id)
        if success:
            await interaction.followup.send(f"✅ Idea `{idea_id}` has been deleted.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Idea `{idea_id}` not found.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(IdeasCog(bot))

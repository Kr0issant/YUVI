import os
import discord
from discord import app_commands, ui
from discord.ext import commands
from typing import Optional

from utils.user_manager import UserManager

class AuthLinkView(ui.View):
    def __init__(self, auth_url: str):
        super().__init__(timeout=None)
        self.add_item(
            ui.Button(
                label="Sign In with Google (@sst.scaler.com)",
                url=auth_url,
                style=discord.ButtonStyle.link,
                emoji="🔐"
            )
        )


async def send_auth_link(interaction: discord.Interaction):
    """Helper to check verification status and send an ephemeral login link."""
    await interaction.response.defer(ephemeral=True)

    discord_id = str(interaction.user.id)
    user_data = await UserManager.get_user(discord_id)

    # 1. Check if already verified
    if user_data:
        email = user_data.get("email", "Unknown")
        full_name = user_data.get("full_name") or user_data.get("name") or "Member"
        
        embed = discord.Embed(
            title="✅ Account Already Linked",
            description=(
                f"Hello {interaction.user.mention}!\n\n"
                f"Your Discord account is already linked with your SST Google account:\n"
                f"• **Email:** `{email}`\n"
                f"• **Name:** `{full_name}`\n\n"
                f"If you are missing your Verified Member role, please contact an admin."
            ),
            color=0x57F287 # Green
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    # 2. Build auth URL
    frontend_url = os.getenv("FRONTEND_AUTH_URL", "http://localhost:3000/auth")
    sep = "&" if "?" in frontend_url else "?"
    auth_url = f"{frontend_url}{sep}discord_id={discord_id}"

    embed = discord.Embed(
        title="🔐 Reinforce Club SST Member Verification",
        description=(
            f"Welcome {interaction.user.mention}!\n\n"
            "To unlock full access to the Reinforce Club Discord server, discussion channels, and Student Project Groups (SPGs), "
            "please authenticate using your official college Google account (**`@sst.scaler.com`**).\n\n"
            "👉 Click the button below to sign in on the website. Once authorized, your role will be granted automatically!"
        ),
        color=0x5865F2 # Blurple
    )
    embed.set_footer(text="Reinforce Club SST • Single Sign-On")
    if interaction.guild and interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)

    view = AuthLinkView(auth_url)
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class AuthPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="Verify with Google (@sst.scaler.com)",
        style=discord.ButtonStyle.primary,
        emoji="🔐",
        custom_id="persistent_auth_button"
    )
    async def auth_button(self, interaction: discord.Interaction, button: ui.Button):
        await send_auth_link(interaction)


class AuthCog(commands.Cog, name="Authentication"):
    """User authentication and Google account linking with Discord."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Register persistent view so button works across bot restarts
        self.bot.add_view(AuthPanelView())

    @app_commands.command(name="setup-auth", description="Deploy the official Reinforce Club Member Verification panel")
    @app_commands.describe(channel="Channel to post the verification panel into (defaults to current channel)")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_auth(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None
    ):
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message("❌ Target must be a text channel.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔐 Reinforce Club SST — Member Verification",
            description=(
                "Welcome to the official **Reinforce Club** Discord server!\n\n"
                "To unlock access to discussion channels, workshop resources, and Student Project Groups (SPGs), "
                "you must link your official student Google account (**`@sst.scaler.com`**).\n\n"
                "**How to Verify:**\n"
                "1. Click the **Verify with Google** button below.\n"
                "2. Click the unique sign-in link generated for your account.\n"
                "3. Authorize with your `@sst.scaler.com` Google account.\n"
                "4. Your **Verified Member** role will be granted automatically!"
            ),
            color=0x5865F2 # Reinforce Blurple
        )
        embed.set_footer(text="Reinforce Club SST • Automated Verification Portal")
        if interaction.guild and interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        await target_channel.send(embed=embed, view=AuthPanelView())
        await interaction.response.send_message(f"✅ Verification panel deployed to {target_channel.mention}!", ephemeral=True)

    @app_commands.command(name="auth", description="Link your @sst.scaler.com Google account to get verified member access")
    async def auth_command(self, interaction: discord.Interaction):
        await send_auth_link(interaction)

    @app_commands.command(name="whois", description="Lookup linked Google account info for a member")
    @app_commands.describe(member="Discord member to inspect")
    @app_commands.checks.has_permissions(administrator=True)
    async def whois_command(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)

        user_data = await UserManager.get_user(str(member.id))
        if not user_data:
            await interaction.followup.send(f"❌ No linked Google account found in database for {member.mention} (`{member.id}`).", ephemeral=True)
            return

        email = user_data.get("email", "N/A")
        full_name = user_data.get("full_name") or user_data.get("name") or "N/A"
        verified_at = user_data.get("verified_at") or user_data.get("created_at") or "N/A"

        embed = discord.Embed(
            title=f"👤 Member Verification Record: {member.name}",
            color=0x5865F2
        )
        embed.add_field(name="Discord User", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="SST Email", value=f"`{email}`", inline=True)
        embed.add_field(name="Full Name", value=f"`{full_name}`", inline=True)
        embed.add_field(name="Verified Date", value=str(verified_at), inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="whois-email", description="Lookup Discord member linked to an SST email")
    @app_commands.describe(email="SST Email address (@sst.scaler.com)")
    @app_commands.checks.has_permissions(administrator=True)
    async def whois_email_command(self, interaction: discord.Interaction, email: str):
        await interaction.response.defer(ephemeral=True)

        user_data = await UserManager.get_user_by_email(email)
        if not user_data:
            await interaction.followup.send(f"❌ No user found in database linked to `{email}`.", ephemeral=True)
            return

        discord_id = user_data.get("id") or user_data.get("discord_id")
        full_name = user_data.get("full_name") or user_data.get("name") or "N/A"

        embed = discord.Embed(
            title=f"📧 Email Record: {email}",
            color=0x5865F2
        )
        embed.add_field(name="Discord ID", value=f"`{discord_id}` (<@{discord_id}>)", inline=False)
        embed.add_field(name="Full Name", value=f"`{full_name}`", inline=True)
        embed.add_field(name="Email", value=f"`{email}`", inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="unlink", description="Unlink a member's Google account and strip the verified role")
    @app_commands.describe(member="Member to unlink")
    @app_commands.checks.has_permissions(administrator=True)
    async def unlink_command(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)

        success = await UserManager.unlink_user(str(member.id))
        if not success:
            await interaction.followup.send(f"⚠️ Could not delete database record for {member.mention}.", ephemeral=True)

        # Remove verified role if present
        role_id = os.getenv("VERIFIED_ROLE_ID")
        role_removed = False
        if role_id and interaction.guild:
            try:
                role = interaction.guild.get_role(int(role_id))
                if role and role in member.roles:
                    await member.remove_roles(role, reason=f"Unlinked by {interaction.user}")
                    role_removed = True
            except Exception as e:
                print(f"[AuthCog] Error removing role: {e}")

        msg = f"✅ Successfully unlinked {member.mention} from database."
        if role_removed:
            msg += " Verified role removed."

        await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AuthCog(bot))
import os
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

class AuthCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="auth", description="DM a user a secure Google auth link")
    async def auth_command(self, interaction: discord.Interaction, target: discord.Member):
        await interaction.response.defer(ephemeral=True)
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{BACKEND_URL}/api/auth/start-link",
                    json={"discord_id": str(target.id)}
                ) as resp:
                    if resp.status != 200:
                        return await interaction.editReply("❌ Backend error generating link.")
                    
                    data = await resp.json()
                    login_url = data["login_url"]
                    
                    await target.send(
                        f"Hello {target.mention}! Click here to authenticate your Google account:\n{login_url}\n*(Link expires in 15 minutes)*"
                    )
                    await interaction.editReply(f"✅ Auth link sent via DM to {target.mention}.")
                    
            except discord.Forbidden:
                await interaction.editReply("❌ Failed to send DM (user has DMs closed).")
            except Exception as e:
                await interaction.editReply(f"❌ Error communicating with backend: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(AuthCog(bot))
import os
import discord
from discord import app_commands
from discord.ext import commands

guild_id_env = os.getenv("GUILD_ID", "1549547403819090011")
GUILD_ID = discord.Object(id=int(guild_id_env)) if guild_id_env.isdigit() else None

class YuviBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.message_content = True

        super().__init__(command_prefix="!", intents=intents)
        self.tree.on_error = self.on_tree_error

    async def on_tree_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        cmd_name = interaction.command.name if interaction.command else "Unknown"
        print(f"[AppCommandError] Error in command '{cmd_name}': {error}")
        import traceback
        traceback.print_exception(type(error), error, error.__traceback__)

        msg = f"❌ An error occurred while executing `/{cmd_name}`: `{error}`"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception as e:
            print(f"[AppCommandError] Failed to send error response to Discord: {e}")

    async def setup_hook(self):
        # Load all cogs from the /cogs directory
        initial_extensions = [
            "cogs.tickets",
            "cogs.auth",
            "cogs.ideas"
        ]
        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
                print(f"Loaded extension: {ext}")
            except Exception as e:
                print(f"Failed to load extension {ext}: {e}")
                import traceback
                traceback.print_exc()
        
        # Sync slash commands
        if GUILD_ID:
            self.tree.copy_global_to(guild=GUILD_ID)
            synced = await self.tree.sync(guild=GUILD_ID)
            print(f"Synced {len(synced)} slash commands to guild {GUILD_ID.id}.")
        else:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash commands globally.")

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")


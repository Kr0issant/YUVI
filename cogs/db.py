import discord
from discord import app_commands
from discord.ext import commands
from firebase_admin import firestore

db = firestore.client()

class DatabaseCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="db-push", description="Push simple key-value to Firestore")
    async def db_push(self, interaction: discord.Interaction, key: str, value: str):
        await interaction.response.defer(ephemeral=False)
        db.collection("app_data").document(key).set({
            "value": value,
            "updated_by": str(interaction.user.id),
            "updated_at": firestore.SERVER_TIMESTAMP
        })
        await interaction.edit_original_response(content=f"Saved `{key}` = `{value}` to Firestore.")

    @app_commands.command(name="db-fetch", description="Fetch key from Firestore")
    async def db_fetch(self, interaction: discord.Interaction, key: str):
        await interaction.response.defer(ephemeral=False)
        doc = db.collection("app_data").document(key).get()
        if doc.exists:
            data = doc.to_dict()
            await interaction.edit_original_response(content=f"Data for `{key}`: ```json\n{data}```")
        else:
            await interaction.edit_original_response(content=f"Key `{key}` not found.")

async def setup(bot: commands.Bot):
    await bot.add_cog(DatabaseCog(bot))
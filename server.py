import os
import asyncio
from contextlib import asynccontextmanager
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

import discord
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel


import firebase_admin
from firebase_admin import credentials
from yuvi_bot import YuviBot

# Initialize Firebase if not already initialized
if not firebase_admin._apps:
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    else:
        firebase_admin.initialize_app()

bot = YuviBot()

class VerifySuccessRequest(BaseModel):
    discord_id: str
    email: str
    name: Optional[str] = None
    secret: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start Discord bot as an asyncio background task
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("[Server] WARNING: DISCORD_TOKEN is not set in environment.")
    
    bot_task = asyncio.create_task(bot.start(token))
    print("[Server] Discord bot background task launched.")
    
    yield

    # Shutdown: Cleanly close Discord bot
    print("[Server] Shutting down Discord bot...")
    await bot.close()
    try:
        await asyncio.wait_for(bot_task, timeout=5.0)
    except asyncio.TimeoutError:
        print("[Server] Bot task shutdown timed out.")
    except Exception as e:
        print(f"[Server] Error during bot shutdown: {e}")


app = FastAPI(
    title="YUVI Bot & Verification Server",
    description="Internal Webhook and API server for Reinforce Club SST Discord Bot",
    version="0.1.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "bot_ready": bot.is_ready(),
        "bot_user": str(bot.user) if bot.user else None
    }


@app.post("/internal/verify-success")
async def verify_success(
    payload: VerifySuccessRequest,
    x_internal_secret: Optional[str] = Header(None)
):
    """
    Internal endpoint called by the Reinforce backend server when a user
    successfully authenticates with their @sst.scaler.com Google account.
    """
    # 1. Optional Secret Authentication
    expected_secret = os.getenv("BOT_INTERNAL_SECRET")
    if expected_secret:
        provided = payload.secret or x_internal_secret
        if provided != expected_secret:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid internal secret")

    # 2. Ensure Bot is Ready
    if not bot.is_ready():
        try:
            await asyncio.wait_for(bot.wait_until_ready(), timeout=10.0)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=503, detail="Discord bot is still starting up, please retry shortly.")

    # 3. Locate Target Guild
    guild_id_env = os.getenv("GUILD_ID")
    guild = bot.get_guild(int(guild_id_env)) if (guild_id_env and guild_id_env.isdigit()) else None
    
    if not guild and bot.guilds:
        guild = bot.guilds[0]

    if not guild:
        raise HTTPException(status_code=500, detail="Bot is not in any Discord server / Guild not found.")

    # 4. Locate Discord Member
    try:
        user_id_int = int(payload.discord_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid discord_id format (must be integer string)")

    member = guild.get_member(user_id_int)
    if not member:
        try:
            member = await guild.fetch_member(user_id_int)
        except discord.NotFound:
            raise HTTPException(status_code=404, detail=f"Member {payload.discord_id} not found in Discord server.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch member {payload.discord_id}: {e}")

    # 5. Locate & Assign Verified Member Role
    verified_role_id = os.getenv("VERIFIED_ROLE_ID")
    verified_role = None

    if verified_role_id and verified_role_id.isdigit():
        verified_role = guild.get_role(int(verified_role_id))

    if not verified_role:
        # Fallback to search role by name
        for r in guild.roles:
            if r.name.lower() in ("verified member", "verified", "member"):
                verified_role = r
                break

    role_assigned = False
    role_name = "None (Role not configured in .env)"

    if verified_role:
        try:
            await member.add_roles(verified_role, reason=f"Google account verified: {payload.email}")
            role_assigned = True
            role_name = verified_role.name
            print(f"[Server] Assigned role '{role_name}' to {member.name} ({member.id})")
        except discord.Forbidden:
            print(f"[Server] ERROR: Missing permissions to assign role '{verified_role.name}' to {member.id}")
            raise HTTPException(status_code=500, detail="Bot lacks permission to assign the verified role (ensure bot role is above verified role in server hierarchy).")
        except Exception as e:
            print(f"[Server] ERROR assigning role: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to assign role: {e}")

    # 6. Send Direct Message Confirmation
    try:
        embed = discord.Embed(
            title="🎉 Welcome to Reinforce Club SST!",
            description=(
                f"Hello {member.mention}!\n\n"
                f"Your Google account (**`{payload.email}`**) has been successfully verified.\n"
                f"You have been granted the **{role_name}** role on Discord.\n\n"
                f"You now have access to member discussion channels, showcase forums, and Student Project Groups (SPGs)!"
            ),
            color=0x57F287
        )
        embed.set_footer(text="Reinforce Club SST • Verification System", icon_url=guild.icon.url if guild.icon else None)
        await member.send(embed=embed)
    except Exception as e:
        print(f"[Server] Note: Could not send DM to user {member.id} (DMs might be closed): {e}")

    return {
        "success": True,
        "discord_id": payload.discord_id,
        "email": payload.email,
        "role_granted": role_name,
        "role_assigned": role_assigned
    }

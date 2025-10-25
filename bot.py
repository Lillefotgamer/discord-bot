import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta
from flask import Flask
import asyncio

# --- CONFIG ---
TOKEN = os.getenv("DISCORD_TOKEN")  # Use Render Environment Variable
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"

# Defaults
config = {
    "ADD_TRIGGER": "part factory tycoon is good",
    "REMOVE_TRIGGER": "part factory tycoon is bad",
    "ADD_AMOUNT": 1,
    "REMOVE_AMOUNT": 1,
    "DAILY_REWARD": 10,
    "DAILY_COOLDOWN_HOURS": 24,
    "CHANNEL_ID": None  # Must be set via admin
}

ROLES = {}  # milestone: role_name

# Load data
if os.path.exists(POINTS_FILE):
    with open(POINTS_FILE, "r") as f:
        user_points = json.load(f)
else:
    user_points = {}

if os.path.exists(DAILY_FILE):
    with open(DAILY_FILE, "r") as f:
        daily_claims = json.load(f)
else:
    daily_claims = {}

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Flask to keep alive on Render
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def save_points():
    with open(POINTS_FILE, "w") as f:
        json.dump(user_points, f)

def save_daily():
    with open(DAILY_FILE, "w") as f:
        json.dump(daily_claims, f)

async def check_roles(member: discord.Member, points: int):
    """Assign roles based on milestone"""
    for milestone, role_name in ROLES.items():
        if points >= milestone:
            role = discord.utils.get(member.guild.roles, name=role_name)
            if role and role not in member.roles:
                await member.add_roles(role)
                await member.send(f"🎉 You reached {milestone} points! You got role **{role.name}**!")

# ---------------- Commands ---------------- #

@tree.command(name="points", description="Check your points")
async def points_cmd(interaction: discord.Interaction):
    pts = user_points.get(str(interaction.user.id), 0)
    await interaction.response.send_message(f"🏅 {interaction.user.mention}, you have **{pts}** points.")

@tree.command(name="daily", description="Claim your daily reward")
async def daily_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    now = datetime.utcnow()
    last_claim = daily_claims.get(user_id)
    cooldown = timedelta(hours=config["DAILY_COOLDOWN_HOURS"])
    if last_claim:
        last_claim_time = datetime.fromisoformat(last_claim)
        if now - last_claim_time < cooldown:
            remaining = cooldown - (now - last_claim_time)
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            await interaction.response.send_message(
                f"⏳ You can claim daily again in {hours}h {minutes}m."
            )
            return

    # Give daily
    user_points[user_id] = user_points.get(user_id, 0) + config["DAILY_REWARD"]
    daily_claims[user_id] = now.isoformat()
    save_points()
    save_daily()
    await check_roles(interaction.user, user_points[user_id])
    await interaction.response.send_message(
        f"🎉 {interaction.user.mention}, you claimed your daily reward of {config['DAILY_REWARD']} points! Total: **{user_points[user_id]}**"
    )

@tree.command(name="gamble", description="Gamble points on red/black")
@app_commands.describe(amount="Amount of points to gamble", color="red or black")
async def gamble(interaction: discord.Interaction, amount: int, color: str):
    user_id = str(interaction.user.id)
    pts = user_points.get(user_id, 0)
    if amount > pts:
        await interaction.response.send_message(f"❌ You don't have that many points.")
        return
    if color.lower() not in ["red", "black"]:
        await interaction.response.send_message("❌ Color must be red or black.")
        return

    import random
    win_color = random.choice(["red", "black"])
    if color.lower() == win_color:
        user_points[user_id] += amount
        await interaction.response.send_message(
            f"🎉 You won! The color was {win_color}. You gain {amount} points! Total: **{user_points[user_id]}**"
        )
    else:
        user_points[user_id] -= amount
        await interaction.response.send_message(
            f"💀 You lost! The color was {win_color}. You lose {amount} points! Total: **{user_points[user_id]}**"
        )
    save_points()
    await check_roles(interaction.user, user_points[user_id])

# ---------------- Admin Commands ---------------- #

def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

@tree.command(name="reset", description="Reset a user's points (Admin)")
@app_commands.describe(user="User to reset")
async def reset_cmd(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You must be an administrator.")
        return
    user_points[str(user.id)] = 0
    save_points()
    await interaction.response.send_message(f"✅ {user.mention}'s points have been reset.")

@tree.command(name="setconfig", description="Change config value (Admin)")
@app_commands.describe(option="Config option", value="New value")
async def setconfig_cmd(interaction: discord.Interaction, option: str, value: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You must be an administrator.")
        return
    if option not in config:
        await interaction.response.send_message("❌ Invalid config option.")
        return
    # Convert numbers to int if possible
    if option in ["ADD_AMOUNT", "REMOVE_AMOUNT", "DAILY_REWARD", "DAILY_COOLDOWN_HOURS"]:
        value = int(value)
    config[option] = value
    await interaction.response.send_message(f"✅ Config {option} set to {value}.")

@tree.command(name="addrole", description="Add a role milestone (Admin)")
@app_commands.describe(points="Points required", role_name="Role to give")
async def addrole_cmd(interaction: discord.Interaction, points: int, role_name: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You must be an administrator.")
        return
    ROLES[points] = role_name
    await interaction.response.send_message(f"✅ Added role milestone: {role_name} at {points} points.")

@tree.command(name="removerole", description="Remove a role milestone (Admin)")
@app_commands.describe(points="Milestone points")
async def removerole_cmd(interaction: discord.Interaction, points: int):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You must be an administrator.")
        return
    if points in ROLES:
        del ROLES[points]
        await interaction.response.send_message(f"✅ Removed role milestone for {points} points.")
    else:
        await interaction.response.send_message("❌ That milestone doesn't exist.")

@tree.command(name="setbot", description="Change bot username/avatar (Admin)")
@app_commands.describe(name="New bot username", avatar_url="Avatar URL")
async def setbot_cmd(interaction: discord.Interaction, name: str = None, avatar_url: str = None):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You must be an administrator.")
        return
    if name:
        await bot.user.edit(username=name)
    if avatar_url:
        import aiohttp, io, base64
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                img = await resp.read()
                await bot.user.edit(avatar=img)
    await interaction.response.send_message("✅ Bot identity updated.")

# ---------------- Help Command ---------------- #
@tree.command(name="help", description="Show commands")
async def help_cmd(interaction: discord.Interaction):
    user_admin = is_admin(interaction)
    help_text = "**User Commands:**\n"
    help_text += "/points - Check your points\n"
    help_text += "/daily - Claim daily reward\n"
    help_text += "/gamble <amount> <color> - Gamble points\n"
    if user_admin:
        help_text += "\n**Admin Commands:**\n"
        help_text += "/reset <user>\n"
        help_text += "/setconfig <option> <value>\n"
        help_text += "/addrole <points> <role_name>\n"
        help_text += "/removerole <points>\n"
        help_text += "/setbot [name] [avatar_url]\n"
    await interaction.response.send_message(help_text)

# ---------------- Run ---------------- #
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

bot.loop.create_task(asyncio.to_thread(app.run, "0.0.0.0", 8080))
bot.run(TOKEN)

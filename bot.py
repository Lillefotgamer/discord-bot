import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime, timedelta

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")  # Put your token in Render environment variable

# Default values (can be changed with admin commands)
CONFIG = {
    "ADD_TRIGGER": "Part Factory Tycoon Is Good",
    "REMOVE_TRIGGER": "Part Factory Tycoon Is Bad",
    "ADD_AMOUNT": 1,
    "REMOVE_AMOUNT": 1,
    "DAILY_REWARD": 10,
    "DAILY_COOLDOWN_HOURS": 24,
    "CHANNEL_ID": None
}

ROLES = {}  # milestone points: role name
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Load points and daily data
if os.path.exists(POINTS_FILE):
    with open(POINTS_FILE) as f:
        user_points = json.load(f)
else:
    user_points = {}

if os.path.exists(DAILY_FILE):
    with open(DAILY_FILE) as f:
        daily_data = json.load(f)
else:
    daily_data = {}

# Helper functions
def save_points():
    with open(POINTS_FILE, "w") as f:
        json.dump(user_points, f)

def save_daily():
    with open(DAILY_FILE, "w") as f:
        json.dump(daily_data, f)

async def check_roles(member: discord.Member):
    points = user_points.get(str(member.id), 0)
    for milestone, role_name in ROLES.items():
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role and points >= milestone and role not in member.roles:
            await member.add_roles(role)
            try:
                await member.send(f"🎉 Congratulations! You reached {milestone} points and got the role **{role.name}**!")
            except:
                pass

# Slash commands
@tree.command(name="points", description="Check your current points")
async def points(interaction: discord.Interaction):
    pts = user_points.get(str(interaction.user.id), 0)
    await interaction.response.send_message(f"🏅 {interaction.user.mention}, you have **{pts}** points.")

@tree.command(name="daily", description="Claim your daily reward")
async def daily(interaction: discord.Interaction):
    now = datetime.utcnow()
    last_claim_str = daily_data.get(str(interaction.user.id))
    if last_claim_str:
        last_claim = datetime.fromisoformat(last_claim_str)
        remaining = timedelta(hours=CONFIG["DAILY_COOLDOWN_HOURS"]) - (now - last_claim)
        if remaining.total_seconds() > 0:
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes = remainder // 60
            return await interaction.response.send_message(
                f"⏳ You have already claimed your daily. Try again in {hours}h {minutes}m."
            )
    # Give daily
    user_points[str(interaction.user.id)] = user_points.get(str(interaction.user.id), 0) + CONFIG["DAILY_REWARD"]
    daily_data[str(interaction.user.id)] = now.isoformat()
    save_points()
    save_daily()
    await check_roles(interaction.user)
    await interaction.response.send_message(
        f"🎉 {interaction.user.mention}, you claimed your daily reward of {CONFIG['DAILY_REWARD']} points! Total: **{user_points[str(interaction.user.id)]}**"
    )

@tree.command(name="gamble", description="Gamble your points. Usage: /gamble amount color")
@app_commands.describe(amount="Amount of points to gamble", color="Red or Black")
async def gamble(interaction: discord.Interaction, amount: int, color: str):
    color = color.lower()
    if amount <= 0:
        return await interaction.response.send_message("❌ You must gamble at least 1 point.")
    user_id = str(interaction.user.id)
    current_points = user_points.get(user_id, 0)
    if current_points < amount:
        return await interaction.response.send_message("❌ You don't have enough points.")
    import random
    win_color = random.choice(["red", "black"])
    if color == win_color:
        current_points += amount
        user_points[user_id] = current_points
        result = f"🎉 You won! The color was {win_color}. You gain {amount} points! Total: **{current_points}**"
    else:
        current_points -= amount
        user_points[user_id] = current_points
        result = f"💀 You lost! The color was {win_color}. You lose {amount} points! Total: **{current_points}**"
    save_points()
    await check_roles(interaction.user)
    await interaction.response.send_message(result)

# Admin-only commands
def is_admin(interaction):
    return interaction.user.guild_permissions.administrator

@tree.command(name="reset", description="Reset a user's points (admin only)")
@app_commands.describe(user="User to reset points")
async def reset(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ You need administrator to do this.")
    user_points[str(user.id)] = 0
    save_points()
    await interaction.response.send_message(f"✅ {user.mention}'s points have been reset.")

@tree.command(name="setconfig", description="Change a config option (admin only)")
@app_commands.describe(option="Option name", value="New value")
async def setconfig(interaction: discord.Interaction, option: str, value: str):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ You need administrator to do this.")
    option = option.upper()
    if option not in CONFIG:
        return await interaction.response.send_message(f"❌ Unknown config option: {option}")
    # Try to convert value to int if possible
    try:
        CONFIG[option] = int(value)
    except:
        CONFIG[option] = value
    await interaction.response.send_message(f"✅ Config `{option}` set to `{CONFIG[option]}`.")

@tree.command(name="addrole", description="Add a role milestone (admin only)")
@app_commands.describe(points="Points required", role_name="Role name")
async def addrole(interaction: discord.Interaction, points: int, role_name: str):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ You need administrator to do this.")
    ROLES[points] = role_name
    await interaction.response.send_message(f"✅ Added role milestone: {points} → {role_name}")

@tree.command(name="removerole", description="Remove a role milestone (admin only)")
@app_commands.describe(points="Points of the role milestone to remove")
async def removerole(interaction: discord.Interaction, points: int):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ You need administrator to do this.")
    if points in ROLES:
        del ROLES[points]
        await interaction.response.send_message(f"✅ Removed role milestone for {points} points")
    else:
        await interaction.response.send_message("❌ No such role milestone.")

# Help command
@tree.command(name="help", description="Show all commands")
async def help_cmd(interaction: discord.Interaction):
    admin = is_admin(interaction)
    embed = discord.Embed(title="Commands", color=discord.Color.blue())
    embed.add_field(name="/points", value="Check your current points", inline=False)
    embed.add_field(name="/daily", value=f"Claim your daily reward ({CONFIG['DAILY_REWARD']} points)", inline=False)
    embed.add_field(name="/gamble", value="Gamble your points. Example: /gamble amount color", inline=False)
    if admin:
        embed.add_field(name="/reset", value="Reset a user's points", inline=False)
        embed.add_field(name="/setconfig", value="Change a config option", inline=False)
        embed.add_field(name="/addrole", value="Add a role milestone", inline=False)
        embed.add_field(name="/removerole", value="Remove a role milestone", inline=False)
    await interaction.response.send_message(embed=embed)

# Run bot
@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {bot.user}")

bot.run(TOKEN)


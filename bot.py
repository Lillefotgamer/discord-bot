import discord
from discord import app_commands
from discord.ext import commands
import json, os, aiohttp
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import random

# ================= CONFIG =================
POINTS_FILE = "points.json"
CONFIG_FILE = "config.json"

# Load or create points file
if not os.path.exists(POINTS_FILE):
    with open(POINTS_FILE, "w") as f:
        json.dump({}, f)

with open(POINTS_FILE, "r") as f:
    user_points = json.load(f)

# Default configuration
default_config = {
    "CHANNEL_ID": None,
    "DAILY_POINTS": 10,
    "DAILY_COOLDOWN_HOURS": 24,
    "GAMBLE_COLORS": ["red", "black", "green"],
    "ROLES": {},
    "BOT_NAME": None,
    "BOT_AVATAR": None
}

# Load or create config file
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w") as f:
        json.dump(default_config, f, indent=2)

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

# ================= FLASK SERVER =================
app = Flask("")

@app.route("/")
def home():
    return "✅ Bot is alive"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

Thread(target=run_flask).start()

# ================= DISCORD BOT =================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

TOKEN = os.environ.get("TOKEN")  # Use environment variable for Render

# ================= HELPERS =================
def save_points():
    with open(POINTS_FILE, "w") as f:
        json.dump(user_points, f, indent=2)

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def get_daily_cooldown(uid):
    last = user_points.get(str(uid), {}).get("last_daily")
    if not last:
        return None
    last_time = datetime.fromisoformat(last)
    elapsed = datetime.utcnow() - last_time
    remaining = timedelta(hours=config["DAILY_COOLDOWN_HOURS"]) - elapsed
    if remaining.total_seconds() <= 0:
        return None
    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m"

async def check_roles(member):
    points = user_points.get(str(member.id), {}).get("points", 0)
    guild = member.guild
    for milestone, role_name in config["ROLES"].items():
        role = discord.utils.get(guild.roles, name=role_name)
        if role and role not in member.roles and points >= milestone:
            await member.add_roles(role)
            await member.send(f"🎉 You reached {milestone} points and got the role **{role.name}**!")

def ensure_user(uid):
    if str(uid) not in user_points:
        user_points[str(uid)] = {"points":0, "last_daily":None}

# ================= EVENTS =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    # Set default bot name and avatar if present
    if config.get("BOT_NAME"):
        await bot.user.edit(username=config["BOT_NAME"])
    if config.get("BOT_AVATAR"):
        async with aiohttp.ClientSession() as session:
            async with session.get(config["BOT_AVATAR"]) as resp:
                data = await resp.read()
                await bot.user.edit(avatar=data)

# ================= SLASH COMMANDS =================
@bot.tree.command(name="points", description="Check your points")
async def points(interaction: discord.Interaction):
    ensure_user(interaction.user.id)
    pts = user_points[str(interaction.user.id)]["points"]
    await interaction.response.send_message(f"🏅 {interaction.user.mention}, you have **{pts}** points.")

@bot.tree.command(name="daily", description="Claim your daily points")
async def daily(interaction: discord.Interaction):
    ensure_user(interaction.user.id)
    cd = get_daily_cooldown(interaction.user.id)
    if cd:
        await interaction.response.send_message(f"⏳ You already claimed your daily! Time left: {cd}")
        return
    user_points[str(interaction.user.id)]["points"] += config["DAILY_POINTS"]
    user_points[str(interaction.user.id)]["last_daily"] = datetime.utcnow().isoformat()
    save_points()
    await check_roles(interaction.user)
    pts = user_points[str(interaction.user.id)]["points"]
    await interaction.response.send_message(f"🎉 {interaction.user.mention}, you claimed your daily reward of {config['DAILY_POINTS']} points! Total: **{pts}**")

@bot.tree.command(name="gamble", description="Gamble points on a color")
@app_commands.describe(amount="Amount of points to gamble", color="Color to bet on")
async def gamble(interaction: discord.Interaction, amount: int, color: str):
    ensure_user(interaction.user.id)
    uid = str(interaction.user.id)
    pts = user_points[uid]["points"]
    color = color.lower()
    if color not in config["GAMBLE_COLORS"]:
        await interaction.response.send_message(f"❌ Invalid color! Options: {', '.join(config['GAMBLE_COLORS'])}")
        return
    if amount <= 0 or amount > pts:
        await interaction.response.send_message(f"❌ Invalid bet amount!")
        return
    result = random.choice(config["GAMBLE_COLORS"])
    if color == result:
        user_points[uid]["points"] += amount
        await interaction.response.send_message(f"🎉 You won! The color was {result}. You gain {amount} points! Total: **{user_points[uid]['points']}**")
    else:
        user_points[uid]["points"] -= amount
        await interaction.response.send_message(f"💀 You lost! The color was {result}. You lose {amount} points! Total: **{user_points[uid]['points']}**")
    save_points()
    await check_roles(interaction.user)

@bot.tree.command(name="help", description="Show all commands")
async def help(interaction: discord.Interaction):
    general_cmds = ["/points", "/daily", "/gamble"]
    admin_cmds = ["/reset <user>", "/setchannel <id>", "/setbot <name> <avatar_url>", "/setconfig <key> <value>", "/addrole <points> <role>", "/removerole <role>"]
    msg = "📜 **Commands:**\n" + "\n".join(general_cmds)
    if interaction.user.guild_permissions.administrator:
        msg += "\n\n🛡️ **Admin Commands:**\n" + "\n".join(admin_cmds)
    await interaction.response.send_message(msg)

# ================= ADMIN COMMANDS =================
@bot.tree.command(name="reset", description="Reset a user's points (Admin only)")
@app_commands.describe(user="User to reset")
async def reset(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need Administrator permissions to use this.")
        return
    ensure_user(user.id)
    user_points[str(user.id)] = {"points":0, "last_daily":None}
    save_points()
    await interaction.response.send_message(f"✅ {user.mention}'s points have been reset.")

@bot.tree.command(name="setchannel", description="Set the channel ID for points")
@app_commands.describe(channel_id="Channel ID to listen to")
async def setchannel(interaction: discord.Interaction, channel_id: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.")
        return
    config["CHANNEL_ID"] = channel_id
    save_config()
    await interaction.response.send_message(f"✅ Channel ID set to {channel_id}")

@bot.tree.command(name="setbot", description="Change bot username and avatar")
@app_commands.describe(name="Bot username", avatar_url="Avatar URL")
async def setbot(interaction: discord.Interaction, name: str = None, avatar_url: str = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.")
        return
    if name:
        await bot.user.edit(username=name)
        config["BOT_NAME"] = name
    if avatar_url:
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                data = await resp.read()
                await bot.user.edit(avatar=data)
                config["BOT_AVATAR"] = avatar_url
    save_config()
    await interaction.response.send_message("✅ Bot identity updated.")

@bot.tree.command(name="setconfig", description="Change config values")
@app_commands.describe(key="Config key", value="New value")
async def setconfig(interaction: discord.Interaction, key: str, value: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.")
        return
    if key not in config:
        await interaction.response.send_message(f"❌ Invalid config key! Options: {', '.join(config.keys())}")
        return
    # convert value types if needed
    try:
        value_eval = int(value)
    except:
        value_eval = value
    config[key] = value_eval
    save_config()
    await interaction.response.send_message(f"✅ Config {key} updated to {value_eval}")

@bot.tree.command(name="addrole", description="Add a role milestone")
@app_commands.describe(points="Points threshold", role="Role name")
async def addrole(interaction: discord.Interaction, points: int, role: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.")
        return
    config["ROLES"][points] = role
    save_config()
    await interaction.response.send_message(f"✅ Role {role} added for {points} points")

@bot.tree.command(name="removerole", description="Remove a role milestone")
@app_commands.describe(role="Role name")
async def removerole(interaction: discord.Interaction, role: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.")
        return
    for k in list(config["ROLES"].keys()):
        if config["ROLES"][k] == role:
            del config["ROLES"][k]
            save_config()
            await interaction.response.send_message(f"✅ Role {role} removed")
            return
    await interaction.response.send_message(f"❌ Role {role} not found")

# ================= SYNC SLASH COMMANDS =================
@bot.event
async def on_guild_join(guild):
    await bot.tree.sync(guild=guild)

# ================= RUN BOT =================
bot.run(TOKEN)




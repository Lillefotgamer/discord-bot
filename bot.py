import discord
from discord import app_commands
from discord.ext import tasks
import json
import os
from datetime import datetime, timedelta

# ---------------- CONFIG ----------------
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 123456789012345678  # Replace with your server ID for slash commands

CONFIG_FILE = "config.json"
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"

# Load or create config
default_config = {
    "ADD_TRIGGER": "Part Factory Tycoon Is Good",
    "REMOVE_TRIGGER": "Part Factory Tycoon Is Bad",
    "ADD_AMOUNT": 1,
    "REMOVE_AMOUNT": 99,
    "DAILY_REWARD": 10,
    "DAILY_COOLDOWN_HOURS": 24,
    "CHANNEL_ID": None,
    "ROLES": {25: "Cool Role 🔥", 100: "Cooler Role 🔥🔥", 250: "Coolest Role 🔥🔥🔥"},
}

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    config = default_config
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

# Load points
if os.path.exists(POINTS_FILE):
    with open(POINTS_FILE, "r") as f:
        user_points = json.load(f)
else:
    user_points = {}

# Load daily claims
if os.path.exists(DAILY_FILE):
    with open(DAILY_FILE, "r") as f:
        daily_claims = json.load(f)
else:
    daily_claims = {}

# ---------------- BOT SETUP ----------------
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# Helper functions
def save_points():
    with open(POINTS_FILE, "w") as f:
        json.dump(user_points, f, indent=4)

def save_daily():
    with open(DAILY_FILE, "w") as f:
        json.dump(daily_claims, f, indent=4)

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

async def check_roles(member: discord.Member):
    points = user_points.get(str(member.id), 0)
    for milestone, role_name in config["ROLES"].items():
        role = discord.utils.get(member.guild.roles, name=role_name)
        if points >= milestone and role not in member.roles:
            await member.add_roles(role)
            await member.send(f"🎉 Congrats! You reached {milestone} points and got the role **{role.name}**!")

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await tree.sync(guild=guild)
    print(f"✅ Bot logged in as {bot.user} and slash commands synced to guild {GUILD_ID}")

# ---------------- SLASH COMMANDS ----------------
@tree.command(name="points", description="Check your points", guild=discord.Object(id=GUILD_ID))
async def points(interaction: discord.Interaction):
    pts = user_points.get(str(interaction.user.id), 0)
    await interaction.response.send_message(f"🏅 {interaction.user.mention}, you have **{pts}** points.")

@tree.command(name="daily", description="Claim your daily points", guild=discord.Object(id=GUILD_ID))
async def daily(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    now = datetime.utcnow()
    last_claim = daily_claims.get(user_id)
    cooldown = timedelta(hours=config["DAILY_COOLDOWN_HOURS"])

    if last_claim:
        last_time = datetime.fromisoformat(last_claim)
        if now < last_time + cooldown:
            remaining = (last_time + cooldown) - now
            hrs, rem = divmod(int(remaining.total_seconds()), 3600)
            mins = rem // 60
            await interaction.response.send_message(f"⏳ You can claim your daily in {hrs}h {mins}m.")
            return

    # Give daily reward
    points_now = user_points.get(user_id, 0) + config["DAILY_REWARD"]
    user_points[user_id] = points_now
    daily_claims[user_id] = now.isoformat()
    save_points()
    save_daily()
    await check_roles(interaction.user)
    await interaction.response.send_message(f"🎉 {interaction.user.mention}, you claimed your daily reward of {config['DAILY_REWARD']} points! Total: **{points_now}**")

@tree.command(name="gamble", description="Gamble points on red or black", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(amount="Points to gamble", color="Color to bet on (red or black)")
async def gamble(interaction: discord.Interaction, amount: int, color: str):
    user_id = str(interaction.user.id)
    points_now = user_points.get(user_id, 0)

    if amount <= 0 or amount > points_now:
        await interaction.response.send_message(f"❌ Invalid amount. You have **{points_now}** points.")
        return

    import random
    color = color.lower()
    if color not in ["red", "black"]:
        await interaction.response.send_message("❌ Choose either red or black.")
        return

    winning_color = random.choice(["red", "black"])
    if color == winning_color:
        user_points[user_id] = points_now + amount
        result = f"🎉 You won! The color was {winning_color}. You gain {amount} points! Total: **{user_points[user_id]}**"
    else:
        user_points[user_id] = points_now - amount
        result = f"💀 You lost! The color was {winning_color}. You lose {amount} points! Total: **{user_points[user_id]}**"

    save_points()
    await check_roles(interaction.user)
    await interaction.response.send_message(result)

# ---------------- ADMIN COMMANDS ----------------
def is_admin(user: discord.Member):
    return user.guild_permissions.administrator

@tree.command(name="reset", description="Reset a user's points", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="User to reset points")
async def reset(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ You must be an administrator to use this.")
        return
    user_points[str(user.id)] = 0
    save_points()
    await interaction.response.send_message(f"✅ {user.mention}'s points have been reset.")

@tree.command(name="setconfig", description="Change a config value", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(option="Config option", value="New value")
async def setconfig(interaction: discord.Interaction, option: str, value: str):
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ You must be an administrator to use this.")
        return
    if option not in config:
        await interaction.response.send_message("❌ Invalid config option.")
        return
    # Convert to int if numeric
    if option in ["ADD_AMOUNT", "REMOVE_AMOUNT", "DAILY_REWARD", "DAILY_COOLDOWN_HOURS", "CHANNEL_ID"]:
        value = int(value)
    config[option] = value
    save_config()
    await interaction.response.send_message(f"✅ Config option {option} set to {value}.")

@tree.command(name="setbot", description="Change bot username/avatar", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(name="New username", avatar_url="URL of new avatar")
async def setbot(interaction: discord.Interaction, name: str = None, avatar_url: str = None):
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ You must be an administrator to use this.")
        return
    if name:
        await bot.user.edit(username=name)
    if avatar_url:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                avatar_bytes = await resp.read()
                await bot.user.edit(avatar=avatar_bytes)
    await interaction.response.send_message("✅ Bot updated.")

@tree.command(name="addrole", description="Add a role milestone", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(points="Points for role", role_name="Role name")
async def addrole(interaction: discord.Interaction, points: int, role_name: str):
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ You must be an administrator to use this.")
        return
    config["ROLES"][points] = role_name
    save_config()
    await interaction.response.send_message(f"✅ Added role milestone {role_name} at {points} points.")

@tree.command(name="removerole", description="Remove a role milestone", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(points="Points of role to remove")
async def removerole(interaction: discord.Interaction, points: int):
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ You must be an administrator to use this.")
        return
    if points in config["ROLES"]:
        role_name = config["ROLES"].pop(points)
        save_config()
        await interaction.response.send_message(f"✅ Removed role milestone {role_name}.")
    else:
        await interaction.response.send_message("❌ No role found at that points value.")

# ---------------- HELP COMMAND ----------------
@tree.command(name="help", description="Show all commands", guild=discord.Object(id=GUILD_ID))
async def help_cmd(interaction: discord.Interaction):
    base_commands = [
        "/points → Check your points",
        "/daily → Claim daily points",
        "/gamble → Gamble points on red/black",
        "/help → Show this help message"
    ]
    admin_commands = [
        "/reset → Reset a user's points",
        "/setconfig → Change a config value",
        "/setbot → Change bot username/avatar",
        "/addrole → Add a role milestone",
        "/removerole → Remove a role milestone"
    ]
    msg = "**Commands:**\n" + "\n".join(base_commands)
    if is_admin(interaction.user):
        msg += "\n\n**Admin Commands:**\n" + "\n".join(admin_commands)
    await interaction.response.send_message(msg)

# ---------------- RUN BOT ----------------
bot.run(TOKEN)



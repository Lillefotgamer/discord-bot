import os, json, random, asyncio
from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands

# Files
CONFIG_FILE = "config.json"
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"

# Load / Save JSON helpers
def load_json(file, default):
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump(default, f, indent=4)
        return default
    with open(file, "r") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

# Default configs
default_config = {
    "ADD_AMOUNT": 1,
    "REMOVE_AMOUNT": 1,
    "DAILY_REWARD": 10,
    "DAILY_COOLDOWN_HOURS": 24,
    "CHANNEL_ID": None
}

config = load_json(CONFIG_FILE, default_config)
points = load_json(POINTS_FILE, {})
daily_claims = load_json(DAILY_FILE, {})

# Intents & bot
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Admin check
def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

# ---------- HELPER FUNCTIONS ----------

def get_points(user_id):
    return points.get(str(user_id), 0)

def add_points(user_id, amount):
    uid = str(user_id)
    points[uid] = points.get(uid, 0) + amount
    save_json(POINTS_FILE, points)
    return points[uid]

def remove_points(user_id, amount):
    uid = str(user_id)
    points[uid] = max(points.get(uid, 0) - amount, 0)
    save_json(POINTS_FILE, points)
    return points[uid]

def can_claim_daily(user_id):
    uid = str(user_id)
    last_claim = daily_claims.get(uid)
    if last_claim is None:
        return True, 0
    last_time = datetime.fromisoformat(last_claim)
    next_time = last_time + timedelta(hours=config["DAILY_COOLDOWN_HOURS"])
    now = datetime.utcnow()
    if now >= next_time:
        return True, 0
    remaining = next_time - now
    hours, remainder = divmod(remaining.total_seconds(), 3600)
    minutes = remainder // 60
    return False, (int(hours), int(minutes))

def update_daily_claim(user_id):
    uid = str(user_id)
    daily_claims[uid] = datetime.utcnow().isoformat()
    save_json(DAILY_FILE, daily_claims)

# ---------- AUTOCOMPLETE ----------

CONFIG_KEYS = list(config.keys())

async def config_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=key, value=key)
        for key in CONFIG_KEYS if current.lower() in key.lower()
    ][:25]

# ---------- SLASH COMMANDS ----------

# /help
@tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction):
    base_commands = [
        "/points - Check your points",
        "/gamble <color> <amount> - Gamble points on red or black",
        "/daily - Claim your daily points"
    ]
    admin_commands = [
        "/reset <user> - Reset a user’s points",
        "/setconfig <option> <value> - Change config values",
        "/setbot <name> <avatar_url> - Change bot username/avatar",
        "/addrole <points> <role_name> - Add role milestone",
        "/removerole <points> - Remove role milestone",
        "/currentconfigurations - Show all config values"
    ]
    desc = "\n".join(base_commands)
    if interaction.user.guild_permissions.administrator:
        desc += "\n\n**Admin Commands:**\n" + "\n".join(admin_commands)
    await interaction.response.send_message(desc, ephemeral=True)

# /points
@tree.command(name="points", description="Check your points")
async def points_command(interaction: discord.Interaction):
    await interaction.response.send_message(f"You have {get_points(interaction.user.id)} points.")

# /gamble
@tree.command(name="gamble", description="Gamble your points on red or black")
@app_commands.describe(color="Choose red or black", amount="Points to gamble")
async def gamble(interaction: discord.Interaction, color: str, amount: int):
    user_points = get_points(interaction.user.id)
    if amount <= 0:
        await interaction.response.send_message("Amount must be positive.", ephemeral=True)
        return
    if amount > user_points:
        await interaction.response.send_message("You don't have enough points.", ephemeral=True)
        return
    color = color.lower()
    if color not in ["red", "black"]:
        await interaction.response.send_message("Color must be red or black.", ephemeral=True)
        return
    result = random.choice(["red", "black"])
    if result == color:
        add_points(interaction.user.id, amount)
        await interaction.response.send_message(f"🎉 You won! The color was {result}. You gain {amount} points! Total: **{get_points(interaction.user.id)}**")
    else:
        remove_points(interaction.user.id, amount)
        await interaction.response.send_message(f"😢 You lost! The color was {result}. You lose {amount} points. Total: **{get_points(interaction.user.id)}**")

# /daily
@tree.command(name="daily", description="Claim your daily points")
async def daily(interaction: discord.Interaction):
    can_claim, remaining = can_claim_daily(interaction.user.id)
    if can_claim:
        add_points(interaction.user.id, config["DAILY_REWARD"])
        update_daily_claim(interaction.user.id)
        await interaction.response.send_message(f"🎉 You claimed your daily reward of {config['DAILY_REWARD']} points! Total: **{get_points(interaction.user.id)}**")
    else:
        await interaction.response.send_message(f"Daily cooldown active. Time remaining: {remaining[0]}h {remaining[1]}m", ephemeral=True)

# /reset
@tree.command(name="reset", description="Reset a user's points (Admin only)")
@app_commands.describe(user="User to reset")
async def reset(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    points[user.id] = 0
    save_json(POINTS_FILE, points)
    await interaction.response.send_message(f"{user.display_name}'s points have been reset.")

# /setconfig
@tree.command(name="setconfig", description="Change a config value (Admin only)")
@app_commands.describe(option="Config option", value="New value")
@app_commands.autocomplete(option=config_autocomplete)
async def setconfig(interaction: discord.Interaction, option: str, value: str):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    if option not in config:
        await interaction.response.send_message(f"Option `{option}` does not exist.", ephemeral=True)
        return
    if value.isdigit():
        value = int(value)
    config[option] = value
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(f"Config `{option}` set to `{value}`.")

# /currentconfigurations
@tree.command(name="currentconfigurations", description="Show current config values (Admin only)")
async def currentconfigs(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    desc = "\n".join(f"{k}: {v}" for k, v in config.items())
    await interaction.response.send_message(f"**Current Configurations:**\n{desc}")

# /setbot
@tree.command(name="setbot", description="Change bot username and avatar (Admin only)")
@app_commands.describe(name="New bot username", avatar_url="Avatar image URL")
async def setbot(interaction: discord.Interaction, name: str = None, avatar_url: str = None):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    try:
        if name:
            await bot.user.edit(username=name)
        if avatar_url:
            import aiohttp, io
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        await bot.user.edit(avatar=data)
        await interaction.response.send_message("Bot identity updated!")
    except Exception as e:
        await interaction.response.send_message(f"Failed: {e}")

# ---------- BOT RUN ----------

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN"))





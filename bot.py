import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
from datetime import datetime, timedelta

# --- CONFIG FILES ---
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"
CONFIG_FILE = "config.json"
ROLES_FILE = "roles.json"

# --- LOAD DATA ---
def load_json(file, default={}):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return default

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

points = load_json(POINTS_FILE)
daily_claims = load_json(DAILY_FILE)
roles = load_json(ROLES_FILE)
config = load_json(CONFIG_FILE, {
    "ADD_MESSAGES": ["You gained {points} points!"],
    "REMOVE_MESSAGES": ["You lost {points} points!"],
    "DAILY_REWARD": 10,
    "DAILY_COOLDOWN_HOURS": 24,
    "CHANNEL_ID": None,
    "BOT_NAME": None,
    "BOT_AVATAR": None
})

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- HELPER FUNCTIONS ---
def get_points(user_id):
    return points.get(str(user_id), 0)

def update_points(user_id, amount):
    points[str(user_id)] = points.get(str(user_id), 0) + amount
    save_json(POINTS_FILE, points)

def can_claim_daily(user_id):
    last_claim = daily_claims.get(str(user_id))
    if not last_claim:
        return True
    last_time = datetime.fromisoformat(last_claim)
    return datetime.utcnow() >= last_time + timedelta(hours=config["DAILY_COOLDOWN_HOURS"])

def time_until_daily(user_id):
    last_claim = daily_claims.get(str(user_id))
    if not last_claim:
        return None
    last_time = datetime.fromisoformat(last_claim)
    remaining = (last_time + timedelta(hours=config["DAILY_COOLDOWN_HOURS"])) - datetime.utcnow()
    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
    minutes = remainder // 60
    return hours, minutes

def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

# --- SLASH COMMANDS ---
@bot.event
async def on_ready():
    if config.get("BOT_NAME"):
        await bot.user.edit(username=config["BOT_NAME"])
    if config.get("BOT_AVATAR"):
        async with bot.session.get(config["BOT_AVATAR"]) as resp:
            avatar = await resp.read()
            await bot.user.edit(avatar=avatar)
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print("Failed to sync commands:", e)
    print(f"{bot.user} is online!")

@bot.tree.command(name="help", description="Show available commands")
async def help_cmd(interaction: discord.Interaction):
    desc = "Available commands:\n"
    desc += "/gamble <amount>\n/daily\n/help\n/currentconfig\n"
    if is_admin(interaction):
        desc += "\nAdmin commands:\n"
        desc += "/reset <user>\n/setconfig <option> <value>\n/setbot <name> <avatar_url>\n/addrole <points> <role_name>\n/removerole <points>\n"
    await interaction.response.send_message(desc, ephemeral=True)

@bot.tree.command(name="points", description="Check your points")
async def points_cmd(interaction: discord.Interaction):
    total = get_points(interaction.user.id)
    await interaction.response.send_message(f"{interaction.user.mention}, you have {total} points!")

@bot.tree.command(name="daily", description="Claim your daily reward")
async def daily_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if not can_claim_daily(user_id):
        hours, minutes = time_until_daily(user_id)
        await interaction.response.send_message(f"You can claim daily again in {hours}h {minutes}m.", ephemeral=True)
        return
    update_points(user_id, config["DAILY_REWARD"])
    daily_claims[user_id] = datetime.utcnow().isoformat()
    save_json(DAILY_FILE, daily_claims)
    await interaction.response.send_message(
        f"{interaction.user.mention}, you claimed your daily reward of {config['DAILY_REWARD']} points! Total: {get_points(user_id)}"
    )

@bot.tree.command(name="gamble", description="Gamble some points")
@app_commands.describe(amount="Amount of points to gamble")
async def gamble(interaction: discord.Interaction, amount: int):
    user_id = str(interaction.user.id)
    total = get_points(user_id)
    if amount > total or amount <= 0:
        await interaction.response.send_message("Invalid amount.", ephemeral=True)
        return
    import random
    win = random.choice([True, False])
    if win:
        update_points(user_id, amount)
        msg = random.choice(config["ADD_MESSAGES"]).replace("{points}", str(amount))
    else:
        update_points(user_id, -amount)
        msg = random.choice(config["REMOVE_MESSAGES"]).replace("{points}", str(amount))
    await interaction.response.send_message(f"{interaction.user.mention} {msg} Total: {get_points(user_id)}")

# --- ADMIN COMMANDS ---
@bot.tree.command(name="reset", description="Reset a user's points")
@app_commands.describe(user="User to reset")
async def reset(interaction: discord.Interaction, user: discord.User):
    if not is_admin(interaction):
        await interaction.response.send_message("You must be an admin.", ephemeral=True)
        return
    points[str(user.id)] = 0
    save_json(POINTS_FILE, points)
    await interaction.response.send_message(f"{user.mention}'s points have been reset.")

@bot.tree.command(name="setconfig", description="Change a config option")
@app_commands.describe(option="Option to set", value="New value")
async def setconfig(interaction: discord.Interaction, option: str, value: str):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    if option not in config:
        await interaction.response.send_message("Invalid option.", ephemeral=True)
        return
    # convert numbers if needed
    if option in ["DAILY_REWARD", "DAILY_COOLDOWN_HOURS"]:
        value = int(value)
    elif option in ["ADD_MESSAGES", "REMOVE_MESSAGES"]:
        value = value.split("|")  # separate multiple messages with |
    config[option] = value
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(f"{option} set to {value}.")

@bot.tree.command(name="setbot", description="Set bot username and avatar")
@app_commands.describe(name="Bot name", avatar_url="Avatar URL")
async def setbot(interaction: discord.Interaction, name: str = None, avatar_url: str = None):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    if name:
        config["BOT_NAME"] = name
        await bot.user.edit(username=name)
    if avatar_url:
        config["BOT_AVATAR"] = avatar_url
        async with bot.session.get(avatar_url) as resp:
            avatar = await resp.read()
            await bot.user.edit(avatar=avatar)
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message("Bot identity updated.")

@bot.tree.command(name="addrole", description="Add a role milestone")
@app_commands.describe(points="Points required", role_name="Role name")
async def addrole(interaction: discord.Interaction, points: int, role_name: str):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    roles[str(points)] = role_name
    save_json(ROLES_FILE, roles)
    await interaction.response.send_message(f"Role milestone added: {role_name} at {points} points.")

@bot.tree.command(name="removerole", description="Remove a role milestone")
@app_commands.describe(points="Points to remove")
async def removerole(interaction: discord.Interaction, points: int):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    roles.pop(str(points), None)
    save_json(ROLES_FILE, roles)
    await interaction.response.send_message(f"Role milestone for {points} points removed.")

@bot.tree.command(name="currentconfig", description="Show current configuration")
async def currentconfig(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    msg = "Current Configurations:\n"
    for key, value in config.items():
        msg += f"{key}: {value}\n"
    await interaction.response.send_message(msg, ephemeral=True)

# --- RUN BOT ---
TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)

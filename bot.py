# bot.py
import os
import json
import random
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta

# ----------------------
# FILES
# ----------------------
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"
CONFIG_FILE = "config.json"
ROLES_FILE = "roles.json"

# ----------------------
# DEFAULT CONFIG
# ----------------------
default_config = {
    "DAILY_AMOUNT": 10,
    "DAILY_COOLDOWN_HOURS": 24,
    "GAMBLE_WIN_CHANCE": 50,  # Percent
    "ADD_MESSAGES": ["You gained {points} points!"],
    "REMOVE_MESSAGES": ["You lost {points} points!"],
    "CHANNEL_ID": None
}

# ----------------------
# HELPER FUNCTIONS
# ----------------------
def load_json(file, default=None):
    try:
        with open(file, "r") as f:
            return json.load(f)
    except:
        return default if default else {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

# ----------------------
# DATA
# ----------------------
points = load_json(POINTS_FILE, {})
daily = load_json(DAILY_FILE, {})
config = load_json(CONFIG_FILE, default_config)
roles = load_json(ROLES_FILE, {})

# ----------------------
# BOT SETUP
# ----------------------
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------------
# UTILITIES
# ----------------------
def get_points(user_id):
    return points.get(str(user_id), 0)

def add_points(user_id, amount):
    points[str(user_id)] = get_points(user_id) + amount
    save_json(POINTS_FILE, points)

def remove_points(user_id, amount):
    points[str(user_id)] = max(0, get_points(user_id) - amount)
    save_json(POINTS_FILE, points)

def is_admin(interaction):
    return interaction.user.guild_permissions.administrator

# ----------------------
# BOT READY
# ----------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# ----------------------
# /help
# ----------------------
@bot.tree.command(name="help", description="Show all commands")
async def help_cmd(interaction: discord.Interaction):
    admin_commands = """
**Admin Commands**
• /reset @user → Reset a user’s points
• /setconfig OPTION VALUE → Change configuration
• /addrole <points> <role_name> → Add role milestone
• /removerole <points> → Remove role milestone
• /setbot [name] [avatar_url] → Change bot identity
• /currentconfig → Show current configuration
"""
    user_commands = """
**User Commands**
• /points → Check your points
• /daily → Claim daily reward
• /gamble <amount> → Gamble points
"""
    msg = user_commands
    if interaction.user.guild_permissions.administrator:
        msg += admin_commands
    await interaction.response.send_message(msg, ephemeral=True)

# ----------------------
# /points
# ----------------------
@bot.tree.command(name="points", description="Check your points")
async def points_cmd(interaction: discord.Interaction):
    total = get_points(interaction.user.id)
    await interaction.response.send_message(f"You have {total} points!")

# ----------------------
# /daily
# ----------------------
@bot.tree.command(name="daily", description="Claim daily reward")
async def daily_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    now = datetime.utcnow()
    last = daily.get(user_id)
    cooldown = timedelta(hours=config.get("DAILY_COOLDOWN_HOURS", 24))

    if last:
        last_dt = datetime.fromisoformat(last)
        remaining = last_dt + cooldown - now
        if remaining.total_seconds() > 0:
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            return await interaction.response.send_message(
                f"You must wait {hours}h {minutes}m to claim daily again."
            )

    add_points(user_id, config.get("DAILY_AMOUNT", 10))
    daily[user_id] = now.isoformat()
    save_json(DAILY_FILE, daily)
    await interaction.response.send_message(
        f"🎉 You claimed your daily reward of {config.get('DAILY_AMOUNT',10)} points! Total: {get_points(user_id)}"
    )

# ----------------------
# /gamble
# ----------------------
@bot.tree.command(name="gamble", description="Gamble points")
@app_commands.describe(amount="Amount of points to gamble")
async def gamble_cmd(interaction: discord.Interaction, amount: int):
    user_id = str(interaction.user.id)
    total = get_points(user_id)
    if amount < 1 or amount > total:
        return await interaction.response.send_message("Invalid gamble amount.")
    win_chance = config.get("GAMBLE_WIN_CHANCE", 50)
    won = random.randint(1, 100) <= win_chance
    if won:
        add_points(user_id, amount)
        msg = random.choice(config.get("ADD_MESSAGES", ["You gained {points} points!"]))
        await interaction.response.send_message(msg.format(points=amount))
    else:
        remove_points(user_id, amount)
        msg = random.choice(config.get("REMOVE_MESSAGES", ["You lost {points} points!"]))
        await interaction.response.send_message(msg.format(points=amount))

# ----------------------
# ADMIN COMMANDS
# ----------------------
@bot.tree.command(name="reset", description="Reset a user’s points (admin)")
@app_commands.describe(user="User to reset")
async def reset_cmd(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction):
        return await interaction.response.send_message("You must be an administrator.", ephemeral=True)
    points[str(user.id)] = 0
    save_json(POINTS_FILE, points)
    await interaction.response.send_message(f"{user.display_name}'s points have been reset.")

@bot.tree.command(name="setconfig", description="Set a config value (admin)")
@app_commands.describe(option="Config option", value="New value")
async def setconfig_cmd(interaction: discord.Interaction, option: str, value: str):
    if not is_admin(interaction):
        return await interaction.response.send_message("You must be an administrator.", ephemeral=True)
    option = option.upper()
    # Handle integers
    if option in ["DAILY_AMOUNT", "DAILY_COOLDOWN_HOURS", "GAMBLE_WIN_CHANCE"]:
        value = int(value)
    # Handle lists for messages
    elif option in ["ADD_MESSAGES", "REMOVE_MESSAGES"]:
        value = value.split(";")  # multiple messages separated by semicolon
    config[option] = value
    save_json(CONFIG_FILE, config)
    await interaction.response.send_message(f"{option} set to {value}")

@bot.tree.command(name="currentconfig", description="Show current config (admin)")
async def currentconfig_cmd(interaction: discord.Interaction):
    if not is_admin(interaction):
        return await interaction.response.send_message("You must be an administrator.", ephemeral=True)
    msg = json.dumps(config, indent=4)
    await interaction.response.send_message(f"```json\n{msg}\n```")

@bot.tree.command(name="addrole", description="Add role milestone (admin)")
@app_commands.describe(points_needed="Points needed", role_name="Role name")
async def addrole_cmd(interaction: discord.Interaction, points_needed: int, role_name: str):
    if not is_admin(interaction):
        return await interaction.response.send_message("You must be an administrator.", ephemeral=True)
    roles[str(points_needed)] = role_name
    save_json(ROLES_FILE, roles)
    await interaction.response.send_message(f"Role milestone added: {points_needed} → {role_name}")

@bot.tree.command(name="removerole", description="Remove role milestone (admin)")
@app_commands.describe(points_needed="Points needed")
async def removerole_cmd(interaction: discord.Interaction, points_needed: int):
    if not is_admin(interaction):
        return await interaction.response.send_message("You must be an administrator.", ephemeral=True)
    roles.pop(str(points_needed), None)
    save_json(ROLES_FILE, roles)
    await interaction.response.send_message(f"Role milestone {points_needed} removed.")

@bot.tree.command(name="setbot", description="Change bot name and avatar (admin)")
@app_commands.describe(name="Bot name", avatar_url="Avatar URL")
async def setbot_cmd(interaction: discord.Interaction, name: str = None, avatar_url: str = None):
    if not is_admin(interaction):
        return await interaction.response.send_message("You must be an administrator.", ephemeral=True)
    if name:
        await bot.user.edit(username=name)
    if avatar_url:
        async with bot.http._HTTPClient__session.get(avatar_url) as resp:
            data = await resp.read()
        await bot.user.edit(avatar=data)
    await interaction.response.send_message("Bot identity updated.")

# ----------------------
# RUN BOT
# ----------------------
TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)

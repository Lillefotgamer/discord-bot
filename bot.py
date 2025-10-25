import os
import json
import random
from datetime import datetime, timedelta
import asyncio

from flask import Flask
from discord.ext import commands, tasks
import discord
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")

# Flask app for Render
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

# Files
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"
ROLES_FILE = "roles.json"
CONFIG_FILE = "config.json"

# Load or initialize JSON
def load_json(file, default):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    else:
        return default

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

points = load_json(POINTS_FILE, {})
daily = load_json(DAILY_FILE, {})
roles = load_json(ROLES_FILE, {})
config = load_json(CONFIG_FILE, {
    "ADD_AMOUNT": 1,
    "REMOVE_AMOUNT": 1,
    "DAILY_REWARD": 10,
    "DAILY_COOLDOWN_HOURS": 24,
    "CHANNEL_ID": None
})

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Helper functions
def get_points(user_id):
    return points.get(str(user_id), 0)

def change_points(user_id, amount):
    points[str(user_id)] = get_points(user_id) + amount
    save_json(POINTS_FILE, points)

def get_daily_remaining(user_id):
    today = datetime.utcnow()
    last = daily.get(str(user_id))
    if last:
        last_time = datetime.fromisoformat(last)
        remaining = last_time + timedelta(hours=config["DAILY_COOLDOWN_HOURS"]) - today
        if remaining.total_seconds() > 0:
            return remaining
    return None

def update_daily(user_id):
    daily[str(user_id)] = datetime.utcnow().isoformat()
    save_json(DAILY_FILE, daily)

# Admin check
def is_admin(interaction):
    return interaction.user.guild_permissions.administrator

# Slash commands
@tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction):
    base_cmds = [
        "/gamble <red|black> <amount> - Gamble your points",
        "/daily - Claim daily reward",
        "/points - Check your points",
    ]
    admin_cmds = [
        "/reset <user> - Reset a user’s points",
        "/setconfig <option> <value> - Change config values",
        "/setbot <name> <avatar_url> - Change bot identity",
        "/addrole <points> <role_name> - Add a role milestone",
        "/removerole <points> - Remove a role milestone",
        "/currentconfig - Show all current config"
    ]
    msg = "Commands:\n" + "\n".join(base_cmds)
    if is_admin(interaction):
        msg += "\n\nAdmin Commands:\n" + "\n".join(admin_cmds)
    await interaction.response.send_message(msg, ephemeral=True)

@tree.command(name="points", description="Check your points")
async def points_command(interaction: discord.Interaction):
    p = get_points(interaction.user.id)
    await interaction.response.send_message(f"{interaction.user.mention}, you have {p} points.")

@tree.command(name="daily", description="Claim your daily reward")
async def daily_command(interaction: discord.Interaction):
    remaining = get_daily_remaining(interaction.user.id)
    if remaining:
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        await interaction.response.send_message(f"You can claim your daily in {hours}h {minutes}m.", ephemeral=True)
        return
    change_points(interaction.user.id, config["DAILY_REWARD"])
    update_daily(interaction.user.id)
    total = get_points(interaction.user.id)
    await interaction.response.send_message(f"🎉 {interaction.user.mention}, you claimed your daily reward of {config['DAILY_REWARD']} points! Total: **{total}**")

@tree.command(name="gamble", description="Gamble your points")
@app_commands.describe(color="Red or Black", amount="Amount of points to gamble")
async def gamble(interaction: discord.Interaction, color: str, amount: int):
    color = color.lower()
    if color not in ["red", "black"]:
        await interaction.response.send_message("Choose 'red' or 'black'!", ephemeral=True)
        return
    current = get_points(interaction.user.id)
    if amount > current:
        await interaction.response.send_message("You don't have enough points.", ephemeral=True)
        return
    win_color = random.choice(["red", "black"])
    if color == win_color:
        change_points(interaction.user.id, amount)
        total = get_points(interaction.user.id)
        await interaction.response.send_message(f"🎉 You won! The color was {win_color}. You gain {amount} points! Total: **{total}**")
    else:
        change_points(interaction.user.id, -amount)
        total = get_points(interaction.user.id)
        await interaction.response.send_message(f"❌ You lost! The color was {win_color}. You lost {amount} points. Total: **{total}**")

# Admin Commands
@tree.command(name="reset", description="Reset a user's points")
@app_commands.describe(user="User to reset")
async def reset(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    points[str(user.id)] = 0
    save_json(POINTS_FILE, points)
    await interaction.response.send_message(f"{user.mention}'s points have been reset.")

@tree.command(name="setconfig", description="Change a config value")
@app_commands.describe(option="Config option", value="New value")
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

@tree.command(name="currentconfig", description="Show all current config")
async def currentconfig(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    msg = "Current configuration:\n" + "\n".join([f"{k}: {v}" for k,v in config.items()])
    await interaction.response.send_message(msg, ephemeral=True)

@tree.command(name="setbot", description="Change bot's username and avatar")
@app_commands.describe(name="New name", avatar_url="New avatar URL")
async def setbot(interaction: discord.Interaction, name: str, avatar_url: str = None):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    try:
        await bot.user.edit(username=name)
        if avatar_url:
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url) as resp:
                    img = await resp.read()
                    await bot.user.edit(avatar=img)
        await interaction.response.send_message("Bot identity updated.")
    except Exception as e:
        await interaction.response.send_message(f"Failed: {e}")

@tree.command(name="addrole", description="Add a role milestone")
@app_commands.describe(points_needed="Points to reach", role_name="Role name")
async def addrole(interaction: discord.Interaction, points_needed: int, role_name: str):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    roles[str(points_needed)] = role_name
    save_json(ROLES_FILE, roles)
    await interaction.response.send_message(f"Role milestone added: {points_needed} → {role_name}")

@tree.command(name="removerole", description="Remove a role milestone")
@app_commands.describe(points_needed="Points of the role to remove")
async def removerole(interaction: discord.Interaction, points_needed: int):
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    if str(points_needed) in roles:
        del roles[str(points_needed)]
        save_json(ROLES_FILE, roles)
        await interaction.response.send_message(f"Removed role milestone: {points_needed}")
    else:
        await interaction.response.send_message(f"No milestone for {points_needed} points.")

# Run
async def main():
    async with bot:
        await bot.start(TOKEN)

# Sync slash commands on ready
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await tree.sync()

# Flask background task for Render uptime
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# Start Flask in background
import threading
threading.Thread(target=run_flask, daemon=True).start()

asyncio.run(main())

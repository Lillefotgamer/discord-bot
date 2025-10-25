import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
from datetime import datetime, timedelta
from flask import Flask

# ------------------ Flask for Render uptime ------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

# ------------------ Bot setup ------------------
TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ------------------ Load JSON files ------------------
def load_json(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

points = load_json("points.json")
daily_claims = load_json("daily.json")
config = load_json("config.json")
role_milestones = load_json("roles.json")

# Set defaults if missing
defaults = {
    "ADD_MESSAGES": ["You gained {amount} points!"],
    "REMOVE_MESSAGES": ["You lost {amount} points!"],
    "DAILY_AMOUNT": 10,
    "DAILY_COOLDOWN_HOURS": 24,
    "CHANNEL_ID": None
}
for k, v in defaults.items():
    if k not in config:
        config[k] = v

# ------------------ Utility ------------------
def get_points(user_id):
    return points.get(str(user_id), 0)

def add_points(user_id, amount):
    uid = str(user_id)
    points[uid] = points.get(uid, 0) + amount
    save_json("points.json", points)

def remove_points(user_id, amount):
    uid = str(user_id)
    points[uid] = max(points.get(uid, 0) - amount, 0)
    save_json("points.json", points)

def is_admin(interaction):
    return interaction.user.guild_permissions.administrator

def format_time(td):
    hours, remainder = divmod(int(td.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m"

# ------------------ Slash Commands ------------------
@tree.command(name="pointscheck", description="Check your points")
async def pointscheck(interaction: discord.Interaction):
    await interaction.response.send_message(f"{interaction.user.mention}, you have {get_points(interaction.user.id)} points!")

@tree.command(name="gamble", description="Gamble some points")
@app_commands.describe(amount="Amount of points to gamble")
async def gamble(interaction: discord.Interaction, amount: int):
    user_points = get_points(interaction.user.id)
    if amount <= 0:
        await interaction.response.send_message("Amount must be greater than 0!")
        return
    if amount > user_points:
        await interaction.response.send_message("You don't have enough points!")
        return
    import random
    win = random.choice([True, False])
    if win:
        add_points(interaction.user.id, amount)
        msg = random.choice(config["ADD_MESSAGES"]).replace("{amount}", str(amount))
    else:
        remove_points(interaction.user.id, amount)
        msg = random.choice(config["REMOVE_MESSAGES"]).replace("{amount}", str(amount))
    await interaction.response.send_message(f"{interaction.user.mention} {msg} Total: {get_points(interaction.user.id)}")

@tree.command(name="daily", description="Claim your daily reward")
async def daily(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    now = datetime.utcnow()
    last_claim = daily_claims.get(user_id)
    cooldown = timedelta(hours=config["DAILY_COOLDOWN_HOURS"])
    if last_claim:
        last_time = datetime.fromisoformat(last_claim)
        if now < last_time + cooldown:
            remaining = (last_time + cooldown) - now
            await interaction.response.send_message(f"Daily already claimed! Time left: {format_time(remaining)}")
            return
    add_points(user_id, config["DAILY_AMOUNT"])
    daily_claims[user_id] = now.isoformat()
    save_json("daily.json", daily_claims)
    await interaction.response.send_message(f"{interaction.user.mention}, you claimed your daily reward of {config['DAILY_AMOUNT']} points! Total: {get_points(user_id)}")

# ------------------ Admin Commands ------------------
@tree.command(name="reset", description="Reset a user's points (Admin only)")
@app_commands.describe(user="User to reset")
async def reset(interaction: discord.Interaction, user: discord.Member):
    if not is_admin(interaction):
        await interaction.response.send_message("You need Administrator to use this!")
        return
    points[str(user.id)] = 0
    save_json("points.json", points)
    await interaction.response.send_message(f"{user.mention}'s points have been reset!")

@tree.command(name="setconfig", description="Set a config option (Admin only)")
@app_commands.describe(option="Config option", value="New value")
async def setconfig(interaction: discord.Interaction, option: str, value: str):
    if not is_admin(interaction):
        await interaction.response.send_message("You need Administrator to use this!")
        return
    option = option.upper()
    if option in ["ADD_MESSAGES", "REMOVE_MESSAGES"]:
        # Split by comma for multiple messages
        config[option] = [x.strip() for x in value.split(",")]
    elif option in ["DAILY_AMOUNT", "DAILY_COOLDOWN_HOURS"]:
        config[option] = int(value)
    elif option == "CHANNEL_ID":
        config[option] = int(value)
    else:
        await interaction.response.send_message(f"Unknown config option: {option}")
        return
    save_json("config.json", config)
    await interaction.response.send_message(f"Config option {option} updated!")

@tree.command(name="setbot", description="Change bot's username and avatar (Admin only)")
@app_commands.describe(name="New name", avatar_url="New avatar URL")
async def setbot(interaction: discord.Interaction, name: str = None, avatar_url: str = None):
    if not is_admin(interaction):
        await interaction.response.send_message("You need Administrator to use this!")
        return
    if name:
        await bot.user.edit(username=name)
    if avatar_url:
        import requests
        r = requests.get(avatar_url)
        await bot.user.edit(avatar=r.content)
    await interaction.response.send_message("Bot identity updated!")

@tree.command(name="currentconfigurations", description="Show current config (Admin only)")
async def currentconfigurations(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("You need Administrator to use this!")
        return
    msg = "Current Configurations:\n"
    for k, v in config.items():
        msg += f"{k}: {v}\n"
    await interaction.response.send_message(msg)

@tree.command(name="addrole", description="Add role milestone (Admin only)")
@app_commands.describe(points="Points needed", role_name="Role name")
async def addrole(interaction: discord.Interaction, points: int, role_name: str):
    if not is_admin(interaction):
        await interaction.response.send_message("You need Administrator to use this!")
        return
    role_milestones[str(points)] = role_name
    save_json("roles.json", role_milestones)
    await interaction.response.send_message(f"Added milestone: {points} points → {role_name}")

@tree.command(name="removerole", description="Remove role milestone (Admin only)")
@app_commands.describe(points="Points of role to remove")
async def removerole(interaction: discord.Interaction, points: int):
    if not is_admin(interaction):
        await interaction.response.send_message("You need Administrator to use this!")
        return
    if str(points) in role_milestones:
        del role_milestones[str(points)]
        save_json("roles.json", role_milestones)
        await interaction.response.send_message(f"Removed milestone for {points} points")
    else:
        await interaction.response.send_message("Milestone not found")

# ------------------ Help Command ------------------
@tree.command(name="help", description="Show help")
async def help_cmd(interaction: discord.Interaction):
    admin = is_admin(interaction)
    msg = "**Commands:**\n"
    msg += "/pointscheck - Check your points\n"
    msg += "/gamble - Gamble points\n"
    msg += "/daily - Claim daily points\n"
    if admin:
        msg += "\n**Admin Commands:**\n"
        msg += "/reset - Reset a user's points\n"
        msg += "/setconfig - Change config options\n"
        msg += "/setbot - Change bot identity\n"
        msg += "/currentconfigurations - Show current config\n"
        msg += "/addrole - Add role milestone\n"
        msg += "/removerole - Remove role milestone\n"
    await interaction.response.send_message(msg)

# ------------------ Bot Ready ------------------
@bot.event
async def on_ready():
    await tree.sync()
    print(f"{bot.user} is online and slash commands synced!")

# ------------------ Run Flask + Bot ------------------
import threading

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask).start()
bot.run(TOKEN)

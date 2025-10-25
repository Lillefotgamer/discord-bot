import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import random
from datetime import datetime, timedelta

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID"))  # Set your server ID as env var

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# File paths
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"
CONFIG_FILE = "config.json"

# Load or initialize data
def load_json(file, default):
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump(default, f)
    with open(file, "r") as f:
        return json.load(f)

points_data = load_json(POINTS_FILE, {})
daily_data = load_json(DAILY_FILE, {})
config_data = load_json(CONFIG_FILE, {
    "DAILY_REWARD": 10,
    "DAILY_COOLDOWN_HOURS": 24,
    "GAMBLE_WIN_CHANCE": 0.5,
    "GAMBLE_WIN_MESSAGES": ["🎉 You won! You gain {points} points!"],
    "GAMBLE_LOSE_MESSAGES": ["😢 You lost! You lose {points} points!"],
    "ADD_TRIGGERS": {"Part Factory Tycoon Is Good": 1},
    "REMOVE_TRIGGERS": {},
    "ROLE_MILESTONES": {}
})

# Helper functions
def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

def get_points(user_id):
    return points_data.get(str(user_id), 0)

def change_points(user_id, amount):
    user_id = str(user_id)
    points_data[user_id] = points_data.get(user_id, 0) + amount
    save_json(POINTS_FILE, points_data)
    return points_data[user_id]

def can_claim_daily(user_id):
    user_id = str(user_id)
    last_claim = daily_data.get(user_id)
    if not last_claim:
        return True
    last_time = datetime.fromisoformat(last_claim)
    return datetime.utcnow() - last_time >= timedelta(hours=config_data["DAILY_COOLDOWN_HOURS"])

def time_until_daily(user_id):
    user_id = str(user_id)
    last_claim = daily_data.get(user_id)
    if not last_claim:
        return 0
    last_time = datetime.fromisoformat(last_claim)
    remaining = timedelta(hours=config_data["DAILY_COOLDOWN_HOURS"]) - (datetime.utcnow() - last_time)
    return max(0, remaining)

# Slash commands
class BotCommands(app_commands.Group):
    @app_commands.command(name="points", description="Check your points")
    async def points(self, interaction: discord.Interaction):
        pts = get_points(interaction.user.id)
        await interaction.response.send_message(f"You have **{pts}** points!")

    @app_commands.command(name="daily", description="Claim your daily reward")
    async def daily(self, interaction: discord.Interaction):
        if can_claim_daily(interaction.user.id):
            pts = change_points(interaction.user.id, config_data["DAILY_REWARD"])
            daily_data[str(interaction.user.id)] = datetime.utcnow().isoformat()
            save_json(DAILY_FILE, daily_data)
            await interaction.response.send_message(
                f"🎉 {interaction.user.mention}, you claimed your daily reward of {config_data['DAILY_REWARD']} points! Total: **{pts}** 🎉"
            )
        else:
            remaining = time_until_daily(interaction.user.id)
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            await interaction.response.send_message(
                f"You already claimed daily! Try again in {hours}h {minutes}m."
            )

    @app_commands.command(name="gamble", description="Gamble your points")
    async def gamble(self, interaction: discord.Interaction, amount: int):
        current = get_points(interaction.user.id)
        if amount <= 0 or amount > current:
            await interaction.response.send_message("Invalid gamble amount!")
            return
        win = random.random() < config_data["GAMBLE_WIN_CHANCE"]
        if win:
            new_pts = change_points(interaction.user.id, amount)
            msg = random.choice(config_data["GAMBLE_WIN_MESSAGES"]).format(points=amount)
        else:
            new_pts = change_points(interaction.user.id, -amount)
            msg = random.choice(config_data["GAMBLE_LOSE_MESSAGES"]).format(points=amount)
        await interaction.response.send_message(f"{msg} Total: **{new_pts}**")

    # Admin commands
    @app_commands.command(name="reset", description="Reset a user's points")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset(self, interaction: discord.Interaction, user: discord.Member):
        points_data[str(user.id)] = 0
        save_json(POINTS_FILE, points_data)
        await interaction.response.send_message(f"{user.mention}'s points have been reset!")

    @app_commands.command(name="setconfig", description="Change a config value")
    @app_commands.checks.has_permissions(administrator=True)
    async def setconfig(self, interaction: discord.Interaction, option: str, value: str):
        if option.upper() in config_data:
            try:
                # Attempt to cast to int or float
                if value.replace('.', '', 1).isdigit():
                    if '.' in value:
                        value = float(value)
                    else:
                        value = int(value)
                elif value.lower() in ["true", "false"]:
                    value = value.lower() == "true"
                config_data[option.upper()] = value
                save_json(CONFIG_FILE, config_data)
                await interaction.response.send_message(f"Config `{option}` updated to `{value}`!")
            except Exception as e:
                await interaction.response.send_message(f"Error: {e}")
        else:
            await interaction.response.send_message(f"Option `{option}` not found!")

    @app_commands.command(name="currentconfig", description="Show current config values")
    @app_commands.checks.has_permissions(administrator=True)
    async def currentconfig(self, interaction: discord.Interaction):
        msg = "Current Configuration:\n"
        for k, v in config_data.items():
            msg += f"**{k}**: {v}\n"
        await interaction.response.send_message(msg)

# Register slash commands
bot.tree.add_command(BotCommands(name="bot", description="Bot commands"))

# Event: message triggers
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    content = message.content.lower()
    added = 0
    removed = 0
    # Check add triggers
    for trigger, pts in config_data.get("ADD_TRIGGERS", {}).items():
        if trigger.lower() in content:
            added += change_points(message.author.id, pts)
    # Check remove triggers
    for trigger, pts in config_data.get("REMOVE_TRIGGERS", {}).items():
        if trigger.lower() in content:
            removed += change_points(message.author.id, -pts)
    if added:
        await message.channel.send(f"{message.author.mention}, you gained {added} points! Total: **{get_points(message.author.id)}**")
    if removed:
        await message.channel.send(f"{message.author.mention}, you lost {removed} points! Total: **{get_points(message.author.id)}**")

# Sync commands on ready
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Error syncing commands: {e}")

bot.run(TOKEN)

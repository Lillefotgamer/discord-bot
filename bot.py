import discord
from discord.ext import commands, tasks
from discord.commands import Option
import json
import os
import random
from datetime import datetime, timedelta

TOKEN = os.getenv("DISCORD_TOKEN")

CONFIG_FILE = "config.json"
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(intents=intents, debug_guilds=None)  # remove debug_guilds for global

# Load JSON
def load_json(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

config_data = load_json(CONFIG_FILE)
points_data = load_json(POINTS_FILE)
daily_data = load_json(DAILY_FILE)

def get_server_config(guild_id):
    return config_data.get(str(guild_id), {
        "CHANNEL_ID": None,
        "DAILY_REWARD": 10,
        "DAILY_COOLDOWN_HOURS": 24,
        "ADD_TRIGGER": [],
        "REMOVE_TRIGGER": [],
        "GAMBLE_WIN_CHANCE": 50,
        "GAMBLE_MULTIPLIER": 2
    })

def is_admin(ctx):
    return ctx.author.guild_permissions.administrator

def add_points(user_id, guild_id, amount):
    guild_id = str(guild_id)
    user_id = str(user_id)
    points_data.setdefault(guild_id, {})
    points_data[guild_id].setdefault(user_id, 0)
    points_data[guild_id][user_id] += amount
    save_json(POINTS_FILE, points_data)
    return points_data[guild_id][user_id]

def can_claim_daily(user_id, guild_id):
    guild_id = str(guild_id)
    user_id = str(user_id)
    cfg = get_server_config(guild_id)
    cooldown = cfg["DAILY_COOLDOWN_HOURS"]
    daily_data.setdefault(guild_id, {})
    last = daily_data[guild_id].get(user_id)
    if last:
        last_time = datetime.fromisoformat(last)
        if datetime.utcnow() < last_time + timedelta(hours=cooldown):
            return False, (last_time + timedelta(hours=cooldown) - datetime.utcnow())
    return True, None

def claim_daily(user_id, guild_id):
    guild_id = str(guild_id)
    user_id = str(user_id)
    cfg = get_server_config(guild_id)
    points = cfg["DAILY_REWARD"]
    total = add_points(user_id, guild_id, points)
    daily_data.setdefault(guild_id, {})
    daily_data[guild_id][user_id] = datetime.utcnow().isoformat()
    save_json(DAILY_FILE, daily_data)
    return points, total

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")

@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return
    guild_id = str(message.guild.id)
    cfg = get_server_config(guild_id)
    if cfg["CHANNEL_ID"] and message.channel.id != cfg["CHANNEL_ID"]:
        return  # Only respond in the configured channel
    content = message.content.lower()
    # Check add triggers
    for trig in cfg["ADD_TRIGGER"]:
        if trig["message"].lower() in content:
            total = add_points(message.author.id, guild_id, trig["points"])
            await message.channel.send(f"{message.author.mention} gained {trig['points']} points! Total: {total}")
            break
    # Check remove triggers
    for trig in cfg["REMOVE_TRIGGER"]:
        if trig["message"].lower() in content:
            total = add_points(message.author.id, guild_id, -trig["points"])
            await message.channel.send(f"{message.author.mention} lost {trig['points']} points! Total: {total}")
            break

# Slash commands

@bot.slash_command(name="daily", description="Claim your daily reward")
async def daily(ctx):
    guild_id = ctx.guild.id
    cfg = get_server_config(guild_id)
    if cfg["CHANNEL_ID"] and ctx.channel.id != cfg["CHANNEL_ID"]:
        await ctx.respond("You can't use commands in this channel.", ephemeral=True)
        return
    can_claim, remaining = can_claim_daily(ctx.author.id, guild_id)
    if not can_claim:
        hours, remainder = divmod(remaining.total_seconds(), 3600)
        minutes = remainder // 60
        await ctx.respond(f"You already claimed daily. Wait {int(hours)}h {int(minutes)}m.")
        return
    points, total = claim_daily(ctx.author.id, guild_id)
    await ctx.respond(f"{ctx.author.mention}, you claimed your daily reward of {points} points! Total: {total}")

@bot.slash_command(name="gamble", description="Gamble your points")
async def gamble(ctx, amount: Option(int, "Amount to gamble", required=True)):
    guild_id = ctx.guild.id
    cfg = get_server_config(guild_id)
    if cfg["CHANNEL_ID"] and ctx.channel.id != cfg["CHANNEL_ID"]:
        await ctx.respond("You can't use commands in this channel.", ephemeral=True)
        return
    user_points = points_data.get(str(guild_id), {}).get(str(ctx.author.id), 0)
    if amount > user_points or amount <= 0:
        await ctx.respond("Invalid amount.")
        return
    chance = cfg.get("GAMBLE_WIN_CHANCE", 50)
    multiplier = cfg.get("GAMBLE_MULTIPLIER", 2)
    if random.randint(1, 100) <= chance:
        gained = amount * (multiplier - 1)
        total = add_points(ctx.author.id, guild_id, gained)
        await ctx.respond(f"🎉 You won! You gain {gained} points! Total: {total}")
    else:
        total = add_points(ctx.author.id, guild_id, -amount)
        await ctx.respond(f"💀 You lost {amount} points! Total: {total}")

@bot.slash_command(name="leaderboard", description="Show server leaderboard")
async def leaderboard(ctx):
    guild_id = str(ctx.guild.id)
    cfg = get_server_config(guild_id)
    if cfg["CHANNEL_ID"] and ctx.channel.id != cfg["CHANNEL_ID"]:
        await ctx.respond("You can't use commands in this channel.", ephemeral=True)
        return
    data = points_data.get(guild_id, {})
    top = sorted(data.items(), key=lambda x: x[1], reverse=True)[:10]
    msg = "🏆 Top 10 Leaderboard:\n"
    for i, (uid, pts) in enumerate(top, 1):
        member = ctx.guild.get_member(int(uid))
        name = member.name if member else "Unknown"
        msg += f"{i}. {name}: {pts}\n"
    await ctx.respond(msg)

@bot.slash_command(name="addmessage", description="Add a trigger message (admin only)")
async def addmessage(ctx, type: Option(str, "ADD or REMOVE"), message: Option(str, "Message text"), points: Option(int, "Points value")):
    if not is_admin(ctx):
        await ctx.respond("You do not have permission to use this command.")
        return
    guild_id = str(ctx.guild.id)
    cfg = get_server_config(guild_id)
    type = type.upper()
    if type not in ["ADD", "REMOVE"]:
        await ctx.respond("Type must be ADD or REMOVE.")
        return
    key = f"{type}_TRIGGER"
    cfg[key].append({"message": message, "points": points})
    config_data[guild_id] = cfg
    save_json(CONFIG_FILE, config_data)
    await ctx.respond(f"Trigger added to {key}: '{message}' → {points} points")

@bot.slash_command(name="removemessage", description="Remove a trigger message (admin only)")
async def removemessage(ctx, type: Option(str, "ADD or REMOVE"), message: Option(str, "Message text")):
    if not is_admin(ctx):
        await ctx.respond("You do not have permission to use this command.")
        return
    guild_id = str(ctx.guild.id)
    cfg = get_server_config(guild_id)
    type = type.upper()
    if type not in ["ADD", "REMOVE"]:
        await ctx.respond("Type must be ADD or REMOVE.")
        return
    key = f"{type}_TRIGGER"
    removed = False
    for trig in cfg[key]:
        if trig["message"].lower() == message.lower():
            cfg[key].remove(trig)
            removed = True
            break
    if removed:
        config_data[guild_id] = cfg
        save_json(CONFIG_FILE, config_data)
        await ctx.respond(f"Trigger removed from {key}: '{message}'")
    else:
        await ctx.respond(f"No trigger found matching '{message}' in {key}")

@bot.slash_command(name="setconfig", description="Set server config (admin only)")
async def setconfig(ctx, option: Option(str, "Config option"), value: Option(str, "Value")):
    if not is_admin(ctx):
        await ctx.respond("You do not have permission to use this command.")
        return
    guild_id = str(ctx.guild.id)
    cfg = get_server_config(guild_id)
    # Convert to correct type
    if option in ["DAILY_REWARD", "DAILY_COOLDOWN_HOURS", "GAMBLE_WIN_CHANCE", "GAMBLE_MULTIPLIER", "CHANNEL_ID"]:
        try:
            value = int(value)
        except:
            await ctx.respond("Value must be an integer.")
            return
    cfg[option] = value
    config_data[guild_id] = cfg
    save_json(CONFIG_FILE, config_data)
    await ctx.respond(f"Config {option} set to {value}")

@bot.slash_command(name="currentconfig", description="Show current server configuration (admin only)")
async def currentconfig(ctx):
    if not is_admin(ctx):
        await ctx.respond("You do not have permission to use this command.")
        return
    guild_id = str(ctx.guild.id)
    cfg = get_server_config(guild_id)
    msg = f"**Server Configuration:**\n"
    msg += f"CHANNEL_ID: {cfg['CHANNEL_ID']}\n"
    msg += f"DAILY_REWARD: {cfg['DAILY_REWARD']}\n"
    msg += f"DAILY_COOLDOWN_HOURS: {cfg['DAILY_COOLDOWN_HOURS']}\n"
    msg += f"GAMBLE_WIN_CHANCE: {cfg['GAMBLE_WIN_CHANCE']}\n"
    msg += f"GAMBLE_MULTIPLIER: {cfg['GAMBLE_MULTIPLIER']}\n"
    msg += "**ADD_TRIGGER:**\n"
    for t in cfg["ADD_TRIGGER"]:
        msg += f"- '{t['message']}' → {t['points']} points\n"
    msg += "**REMOVE_TRIGGER:**\n"
    for t in cfg["REMOVE_TRIGGER"]:
        msg += f"- '{t['message']}' → {t['points']} points\n"
    await ctx.respond(msg)

bot.run(TOKEN)


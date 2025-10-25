import discord
from discord.ext import commands
import json, os, random
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import aiohttp

# --- FILES ---
POINTS_FILE = "points.json"
CONFIG_FILE = "config.json"
TOKEN = "YOUR_BOT_TOKEN_HERE"  # replace with your token

# --- DEFAULT CONFIG ---
default_config = {
    "ADD_TRIGGER": "part factory tycoon is good",
    "REMOVE_TRIGGER": "part factory tycoon is bad",
    "ADD_AMOUNT": 1,
    "REMOVE_AMOUNT": 99,
    "DAILY_REWARD": 10,
    "DAILY_COOLDOWN_HOURS": 24,
    "ROLES": {},
    "CHANNEL_ID": None,  # Must be set manually
    "BOT_NAME": None,    # Defaults to current Discord username
    "BOT_AVATAR": None   # Defaults to current Discord avatar
}

# --- INIT FILES ---
if not os.path.exists(POINTS_FILE):
    with open(POINTS_FILE, "w") as f:
        json.dump({}, f)

if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w") as f:
        json.dump(default_config, f, indent=2)

def load_points():
    with open(POINTS_FILE, "r") as f:
        return json.load(f)

def save_points(data):
    with open(POINTS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

user_points = load_points()
config = load_config()

# --- DISCORD SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- FLASK SERVER ---
app = Flask("")
@app.route("/")
def home():
    return "✅ Bot is alive"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

Thread(target=run_flask).start()

# --- HELPERS ---
def get_daily_cooldown(last_claim):
    if not last_claim:
        return None
    now = datetime.utcnow()
    try:
        last_time = datetime.fromisoformat(last_claim)
    except ValueError:
        return None
    elapsed = now - last_time
    remaining = timedelta(hours=config["DAILY_COOLDOWN_HOURS"]) - elapsed
    if remaining.total_seconds() <= 0:
        return None
    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m"

async def check_roles(member, points_amount):
    for milestone_str, role_name in config["ROLES"].items():
        milestone = int(milestone_str)
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role and points_amount >= milestone and role not in member.roles:
            await member.add_roles(role)
            await member.send(f"🎉 You reached {milestone} points and got the role **{role.name}**!")

# --- EVENTS ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    # Apply bot name/avatar if configured
    if config.get("BOT_NAME") and bot.user.name != config["BOT_NAME"]:
        await bot.user.edit(username=config["BOT_NAME"])
    if config.get("BOT_AVATAR"):
        async with aiohttp.ClientSession() as session:
            async with session.get(config["BOT_AVATAR"]) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    await bot.user.edit(avatar=data)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Check if CHANNEL_ID is set
    channel_id = config.get("CHANNEL_ID")
    if not channel_id:
        return  # No channel set, ignore all messages

    if message.channel.id != channel_id:
        return

    uid = str(message.author.id)
    user_points.setdefault(uid, {"points": 0, "last_daily": None})
    changed = False
    text = message.content.lower()

    if text == config["ADD_TRIGGER"].lower():
        user_points[uid]["points"] += config["ADD_AMOUNT"]
        await message.channel.send(f"🎉 {message.author.mention} gained {config['ADD_AMOUNT']} point(s)! Total: **{user_points[uid]['points']}**")
        changed = True
    elif text == config["REMOVE_TRIGGER"].lower():
        user_points[uid]["points"] = max(0, user_points[uid]["points"] - config["REMOVE_AMOUNT"])
        await message.channel.send(f"💀 {message.author.mention} lost {config['REMOVE_AMOUNT']} points! Total: **{user_points[uid]['points']}**")
        changed = True

    if changed:
        save_points(user_points)
        await check_roles(message.author, user_points[uid]["points"])

    await bot.process_commands(message)

# --- COMMANDS ---
@bot.command()
async def points(ctx):
    uid = str(ctx.author.id)
    user_points.setdefault(uid, {"points": 0, "last_daily": None})
    await ctx.send(f"🏅 {ctx.author.mention}, you have **{user_points[uid]['points']}** points.")

@bot.command()
async def daily(ctx):
    uid = str(ctx.author.id)
    user_points.setdefault(uid, {"points": 0, "last_daily": None})
    last_claim = user_points[uid]["last_daily"]

    remaining = get_daily_cooldown(last_claim)
    if remaining:
        return await ctx.send(f"🕒 {ctx.author.mention}, you already claimed your daily reward! Try again in **{remaining}**.")

    user_points[uid]["points"] += config["DAILY_REWARD"]
    user_points[uid]["last_daily"] = datetime.utcnow().isoformat()
    save_points(user_points)
    await ctx.send(f"🎉 {ctx.author.mention}, you claimed your daily reward of {config['DAILY_REWARD']} points! Total: **{user_points[uid]['points']}**")

@bot.command()
async def gamble(ctx, amount: int, color: str):
    uid = str(ctx.author.id)
    user_points.setdefault(uid, {"points": 0, "last_daily": None})
    total = user_points[uid]["points"]

    if amount <= 0 or amount > total:
        return await ctx.send(f"🚫 {ctx.author.mention}, invalid bet amount.")

    color = color.lower()
    if color not in ["red", "black"]:
        return await ctx.send("❌ Please choose `red` or `black`.")

    result = random.choice(["red", "black"])
    if color == result:
        user_points[uid]["points"] += amount
        await ctx.send(f"🎉 You won! The color was **{result}**. You gain {amount} point(s)! Total: **{user_points[uid]['points']}**")
    else:
        user_points[uid]["points"] -= amount
        await ctx.send(f"❌ You lost! The color was **{result}**. You lose {amount} point(s)! Total: **{user_points[uid]['points']}**")
    save_points(user_points)

# --- ADMIN COMMANDS ---
@bot.command()
@commands.has_permissions(administrator=True)
async def reset(ctx, member: discord.Member):
    uid = str(member.id)
    user_points[uid] = {"points": 0, "last_daily": None}
    save_points(user_points)
    await ctx.send(f"🧹 {member.mention}'s points have been reset to 0.")

@bot.command()
@commands.has_permissions(administrator=True)
async def setconfig(ctx, option: str, *, value):
    option = option.upper()
    if option not in config:
        return await ctx.send(f"❌ Invalid option. Options: {', '.join(config.keys())}")

    if option in ["ADD_AMOUNT","REMOVE_AMOUNT","DAILY_REWARD","DAILY_COOLDOWN_HOURS","CHANNEL_ID"]:
        try: value = int(value)
        except: return await ctx.send("❌ Value must be a number.")

    config[option] = value
    save_config(config)
    await ctx.send(f"✅ Config `{option}` updated to `{value}`")

@bot.command()
@commands.has_permissions(administrator=True)
async def setbot(ctx, name: str = None, avatar_url: str = None):
    if name:
        await bot.user.edit(username=name)
        config["BOT_NAME"] = name
    if avatar_url:
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    await bot.user.edit(avatar=data)
                    config["BOT_AVATAR"] = avatar_url
    save_config(config)
    await ctx.send("✅ Bot identity updated successfully.")

@bot.command()
@commands.has_permissions(administrator=True)
async def addrole(ctx, points: int, *, role_name: str):
    config["ROLES"][str(points)] = role_name
    save_config(config)
    await ctx.send(f"✅ Added role milestone: {points} points → {role_name}")

@bot.command()
@commands.has_permissions(administrator=True)
async def removerole(ctx, points: int):
    if str(points) in config["ROLES"]:
        role = config["ROLES"].pop(str(points))
        save_config(config)
        await ctx.send(f"🗑 Removed role milestone: {points} → {role}")
    else:
        await ctx.send("❌ No such milestone found.")

bot.run(TOKEN)


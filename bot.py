import discord
from discord.ext import commands
import random
import datetime
import json
import os
from flask import Flask
from threading import Thread

# --- CONFIG ---
TOKEN = os.getenv("DISCORD_TOKEN")  # Set this in Replit Secrets
CHANNEL_ID = "1431309661461680260"

ADD_TRIGGER = "Part Factory Tycoon Is Good"
REMOVE_TRIGGER = "Part Factory Tycoon Is Bad"
ADD_AMOUNT = 1
REMOVE_AMOUNT = 99

ROLES = {
    25: "Cool Role 🔥",
    100: "Cooler Role 🔥🔥",
    250: "Coolest Role 🔥🔥🔥"
}

DAILY_BONUS = 10
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"
# ----------------

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Load points
if os.path.exists(POINTS_FILE):
    with open(POINTS_FILE, "r") as f:
        user_points = json.load(f)
else:
    user_points = {}

if os.path.exists(DAILY_FILE):
    with open(DAILY_FILE, "r") as f:
        last_daily = json.load(f)
else:
    last_daily = {}

def save_points():
    with open(POINTS_FILE, "w") as f:
        json.dump(user_points, f)

def save_daily():
    with open(DAILY_FILE, "w") as f:
        json.dump(last_daily, f)

# --- Roles check ---
async def check_roles(member: discord.Member, points: int):
    guild = member.guild
    for milestone, role_name in ROLES.items():
        role = discord.utils.get(guild.roles, name=role_name)
        if points >= milestone and role and role not in member.roles:
            await member.add_roles(role)
            await member.send(f"🎉 Congrats! You reached {milestone} points and got the role **{role.name}**!")
        elif points < milestone and role and role in member.roles:
            await member.remove_roles(role)
            await member.send(f"⚠️ You no longer have enough points for **{role.name}**.")

# --- Web server for UptimeRobot ---
app = Flask('')
@app.route('/')
def home():
    return "Bot is running!"
def run():
    app.run(host='0.0.0.0', port=3000)
Thread(target=run).start()

# --- Bot events ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or str(message.channel.id) != CHANNEL_ID:
        return

    user_id = str(message.author.id)
    current_points = user_points.get(user_id, 0)
    msg_content = message.content.lower()
    changed = False

    if msg_content == ADD_TRIGGER.lower():
        current_points += ADD_AMOUNT
        user_points[user_id] = current_points
        save_points()
        await message.channel.send(f"🎉 {message.author.mention} gained {ADD_AMOUNT} points! Total: **{current_points}**")
        changed = True
    elif msg_content == REMOVE_TRIGGER.lower():
        current_points -= REMOVE_AMOUNT
        if current_points < 0: current_points = 0
        user_points[user_id] = current_points
        save_points()
        await message.channel.send(f"💀 {message.author.mention} lost {REMOVE_AMOUNT} points! Total: **{current_points}**")
        changed = True

    if changed:
        await check_roles(message.author, current_points)

    await bot.process_commands(message)

# --- Commands ---
@bot.command()
async def points(ctx):
    user_id = str(ctx.author.id)
    pts = user_points.get(user_id, 0)
    await ctx.send(f"🏅 {ctx.author.mention}, you have **{pts}** points.")

@bot.command()
async def daily(ctx):
    user_id = str(ctx.author.id)
    now = datetime.datetime.utcnow().timestamp()
    last_time = last_daily.get(user_id, 0)
    if now - last_time < 86400:
        await ctx.send("⏳ You have already claimed your daily bonus!")
        return
    user_points[user_id] = user_points.get(user_id, 0) + DAILY_BONUS
    last_daily[user_id] = now
    save_points()
    save_daily()
    await ctx.send(f"🎁 {ctx.author.mention} claimed {DAILY_BONUS} points! Total: {user_points[user_id]}")
    await check_roles(ctx.author, user_points[user_id])

@bot.command()
async def gamble(ctx, amount: int, choice: str):
    user_id = str(ctx.author.id)
    current_points = user_points.get(user_id, 0)

    if amount <= 0 or amount > current_points:
        await ctx.send("❌ Invalid amount to gamble.")
        return

    choice = choice.lower()
    if choice not in ["red", "black"]:
        await ctx.send("❌ Choice must be 'red' or 'black'.")
        return

    result = random.choice(["red", "black"])
    if choice == result:
        winnings = amount * 2
        current_points += winnings
        await ctx.send(f"🎉 You won! The color was {result}. You gain {winnings} points! Total: **{current_points}**")
    else:
        current_points -= amount
        if current_points < 0: current_points = 0
        await ctx.send(f"💀 You lost! The color was {result}. You lose {amount} points! Total: **{current_points}**")

    user_points[user_id] = current_points
    save_points()
    await check_roles(ctx.author, current_points)

# --- Run bot ---
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()
bot.run(TOKEN)


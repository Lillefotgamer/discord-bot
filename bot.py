import discord
from discord.ext import commands
import json
from datetime import datetime
import random
from flask import Flask
from threading import Thread
import os

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")  # Use environment variable for security
CHANNEL_ID = 1431309661461680260  # Replace with your channel ID

ADD_TRIGGER = "Part Factory Tycoon Is Good"
REMOVE_TRIGGER = "Part Factory Tycoon Is Bad"
ADD_AMOUNT = 1
REMOVE_AMOUNT = 99

DAILY_AMOUNT = 10  # Daily reward

ROLES = {
    25: "Cool Role 🔥",
    100: "Cooler Role 🔥🔥",
    250: "Coolest Role 🔥🔥🔥"
}
# ----------------------

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Load points
if os.path.exists("points.json"):
    with open("points.json", "r") as f:
        user_points = json.load(f)
else:
    user_points = {}

# Load daily
if os.path.exists("daily.json"):
    with open("daily.json", "r") as f:
        daily_data = json.load(f)
else:
    daily_data = {}

# --- Flask server to stay online ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

# --- Helper Functions ---
async def check_roles(member: discord.Member, points: int):
    guild = member.guild
    for milestone, role_name in ROLES.items():
        if points >= milestone:
            role = discord.utils.get(guild.roles, name=role_name)
            if role and role not in member.roles:
                await member.add_roles(role)
                await member.send(f"🎉 Congratulations! You reached {milestone} points and got the role **{role.name}**!")

def save_points():
    with open("points.json", "w") as f:
        json.dump(user_points, f)

def save_daily():
    with open("daily.json", "w") as f:
        json.dump(daily_data, f)

# --- Events ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.channel.id != CHANNEL_ID:
        return

    user_id = str(message.author.id)
    current_points = user_points.get(user_id, 0)
    changed = False
    content_lower = message.content.lower()

    # Add points
    if content_lower == ADD_TRIGGER.lower():
        current_points += ADD_AMOUNT
        user_points[user_id] = current_points
        await message.channel.send(f"🎉 {message.author.mention} gained {ADD_AMOUNT} points! Total: **{current_points}**")
        changed = True

    # Remove points
    elif content_lower == REMOVE_TRIGGER.lower():
        current_points -= REMOVE_AMOUNT
        if current_points < 0:
            current_points = 0
        user_points[user_id] = current_points
        await message.channel.send(f"💀 {message.author.mention} lost {REMOVE_AMOUNT} points! Total: **{current_points}**")
        changed = True

    if changed:
        await check_roles(message.author, current_points)
        save_points()

    # Only process commands that start with the prefix
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)

# --- Commands ---
@bot.command()
async def points(ctx):
    pts = user_points.get(str(ctx.author.id), 0)
    await ctx.send(f"🏅 {ctx.author.mention}, you have **{pts}** points.")

@bot.command()
async def daily(ctx):
    user_id = str(ctx.author.id)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    last_claim = daily_data.get(user_id)
    if last_claim == today:
        await ctx.send(f"⏳ {ctx.author.mention}, you already claimed your daily reward today!")
        return

    current_points = user_points.get(user_id, 0) + DAILY_AMOUNT
    user_points[user_id] = current_points
    daily_data[user_id] = today
    save_points()
    save_daily()
    await ctx.send(f"🎉 {ctx.author.mention}, you claimed your daily reward of {DAILY_AMOUNT} points! Total: **{current_points}**")
    await check_roles(ctx.author, current_points)

@bot.command()
async def gamble(ctx, amount: int, color: str):
    user_id = str(ctx.author.id)
    current_points = user_points.get(user_id, 0)

    if amount > current_points or amount <= 0:
        await ctx.send(f"💀 {ctx.author.mention}, you can't gamble that amount!")
        return

    color = color.lower()
    if color not in ["red", "black"]:
        await ctx.send("⚠️ You must choose 'red' or 'black'.")
        return

    result = random.choice(["red", "black"])
    if color == result:
        # Win: add exactly the bet amount (effectively doubling)
        current_points += amount
        user_points[user_id] = current_points
        save_points()
        await ctx.send(f"🎲 {ctx.author.mention}, the result was **{result}**! You won **{amount}** points! Total: **{current_points}**")
    else:
        # Lose: subtract the bet
        current_points -= amount
        if current_points < 0:
            current_points = 0
        user_points[user_id] = current_points
        save_points()
        await ctx.send(f"🎲 {ctx.author.mention}, the result was **{result}**! You lost **{amount}** points! Total: **{current_points}**")

    await check_roles(ctx.author, current_points)

# --- Admin command to reset a user ---
@bot.command()
@commands.has_permissions(administrator=True)
async def reset(ctx, member: discord.Member):
    user_id = str(member.id)
    user_points[user_id] = 0
    daily_data[user_id] = None
    save_points()
    save_daily()
    await ctx.send(f"🛠️ {ctx.author.mention} reset points and daily for {member.mention}.")

@reset.error
async def reset_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(f"❌ {ctx.author.mention}, you need Administrator permissions to use this command.")

# --- Run Bot ---
bot.run(TOKEN)


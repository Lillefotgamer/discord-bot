import discord
from discord.ext import commands
import json, os, random
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")  # Set in Render environment
CHANNEL_ID = 1431309661461680260
ADD_TRIGGER = "part factory tycoon is good"
REMOVE_TRIGGER = "part factory tycoon is bad"
ADD_AMOUNT = 1
REMOVE_AMOUNT = 99
DAILY_REWARD = 10
DAILY_COOLDOWN_HOURS = 24

ROLES = {
    25: "Cool Role 🔥",
    100: "Cooler Role 🔥🔥",
    250: "Coolest Role 🔥🔥🔥"
}

# --- FILE SETUP ---
POINTS_FILE = "points.json"
if not os.path.exists(POINTS_FILE):
    with open(POINTS_FILE, "w") as f:
        json.dump({}, f)

def load_points():
    with open(POINTS_FILE, "r") as f:
        return json.load(f)

def save_points(data):
    with open(POINTS_FILE, "w") as f:
        json.dump(data, f, indent=2)

user_points = load_points()

# --- DISCORD SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- FLASK SERVER FOR KEEP-ALIVE ---
app = Flask("")
@app.route("/")
def home():
    return "✅ Bot is alive"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

Thread(target=run_flask).start()

# --- HELPERS ---
def get_daily_cooldown(last_claim):
    now = datetime.utcnow()
    elapsed = now - datetime.fromisoformat(last_claim)
    remaining = timedelta(hours=DAILY_COOLDOWN_HOURS) - elapsed
    if remaining.total_seconds() <= 0:
        return None
    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m"

async def check_roles(member, points_amount):
    for milestone, role_name in ROLES.items():
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role and points_amount >= milestone and role not in member.roles:
            await member.add_roles(role)
            await member.send(f"🎉 You reached {milestone} points and got the role **{role.name}**!")

# --- EVENTS ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot or message.channel.id != CHANNEL_ID:
        return

    user_id = str(message.author.id)
    user_points.setdefault(user_id, {"points": 0, "last_daily": None})
    changed = False
    text = message.content.lower()

    if text == ADD_TRIGGER:
        user_points[user_id]["points"] += ADD_AMOUNT
        await message.channel.send(f"🎉 {message.author.mention} gained {ADD_AMOUNT} point(s)! Total: **{user_points[user_id]['points']}**")
        changed = True

    elif text == REMOVE_TRIGGER:
        user_points[user_id]["points"] = max(0, user_points[user_id]["points"] - REMOVE_AMOUNT)
        await message.channel.send(f"💀 {message.author.mention} lost {REMOVE_AMOUNT} points! Total: **{user_points[user_id]['points']}**")
        changed = True

    if changed:
        save_points(user_points)
        await check_roles(message.author, user_points[user_id]["points"])

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

    if last_claim:
        remaining = get_daily_cooldown(last_claim)
        if remaining:
            return await ctx.send(f"🕒 {ctx.author.mention}, you already claimed your daily reward! Try again in **{remaining}**.")

    user_points[uid]["points"] += DAILY_REWARD
    user_points[uid]["last_daily"] = datetime.utcnow().isoformat()
    save_points(user_points)
    await ctx.send(f"🎉 {ctx.author.mention}, you claimed your daily reward of {DAILY_REWARD} points! Total: **{user_points[uid]['points']}**")

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

@bot.command()
@commands.has_permissions(administrator=True)
async def reset(ctx, member: discord.Member):
    uid = str(member.id)
    user_points[uid] = {"points": 0, "last_daily": None}
    save_points(user_points)
    await ctx.send(f"🧹 {member.mention}'s points have been reset to 0.")

@reset.error
async def reset_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("🚫 You don’t have permission to use this command.")

@bot.command()
async def leaderboard(ctx):
    if not user_points:
        return await ctx.send("📉 Nobody has any points yet!")

    top_users = sorted(user_points.items(), key=lambda x: x[1]["points"], reverse=True)[:10]
    description = ""
    for i, (uid, data) in enumerate(top_users, start=1):
        user = await bot.fetch_user(int(uid))
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}️⃣"
        description += f"{medal} **{user.name}** — {data['points']} points\n"

    embed = discord.Embed(title="🏆 Leaderboard (Top 10)", description=description, color=discord.Color.gold())
    await ctx.send(embed=embed)

# --- RUN ---
bot.run(TOKEN)

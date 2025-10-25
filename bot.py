import discord
from discord.ext import commands
import json, random, datetime, os
from flask import Flask
from threading import Thread

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"

def load_json(filename):
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump({}, f)
    with open(filename, "r") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

points = load_json(POINTS_FILE)
daily = load_json(DAILY_FILE)

# Flask keep-alive (Render/UptimeRobot)
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    msg = message.content.lower()
    user_id = str(message.author.id)
    if user_id not in points:
        points[user_id] = 0

    # Gain/loss system
    if "part factory tycoon is good" in msg:
        points[user_id] += 1
        await message.channel.send(f"🎉 {message.author.mention} gained 1 point! Total: **{points[user_id]}**")
    elif "part factory tycoon is bad" in msg:
        points[user_id] = max(0, points[user_id] - 99)
        await message.channel.send(f"💀 {message.author.mention} lost 99 points! Total: **{points[user_id]}**")

    save_json(POINTS_FILE, points)
    await bot.process_commands(message)

@bot.command()
async def pointscheck(ctx):
    user_id = str(ctx.author.id)
    total = points.get(user_id, 0)
    await ctx.send(f"💰 {ctx.author.mention}, you have **{total}** points.")

@bot.command()
async def daily(ctx):
    user_id = str(ctx.author.id)
    now = datetime.datetime.utcnow()
    last_claim = daily.get(user_id)

    if last_claim:
        elapsed = (now - datetime.datetime.fromisoformat(last_claim)).total_seconds()
        if elapsed < 86400:  # 24 hours
            remaining = 86400 - elapsed
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            seconds = int(remaining % 60)
            await ctx.send(
                f"🕒 {ctx.author.mention}, you already claimed your daily! "
                f"Try again in **{hours}h {minutes}m {seconds}s**."
            )
            return

    points[user_id] = points.get(user_id, 0) + 10
    daily[user_id] = now.isoformat()
    save_json(POINTS_FILE, points)
    save_json(DAILY_FILE, daily)
    await ctx.send(f"🎉 {ctx.author.mention}, you claimed your daily reward of 10 points! Total: **{points[user_id]}**")

@bot.command()
async def gamble(ctx, amount: int, color: str = None):
    user_id = str(ctx.author.id)
    if points.get(user_id, 0) < amount:
        await ctx.send(f"🚫 {ctx.author.mention}, you don’t have enough points to gamble that amount!")
        return

    color = color.lower() if color else random.choice(["red", "black"])
    outcome = random.choice(["red", "black"])
    if outcome == color:
        points[user_id] += amount  # win = +amount
        await ctx.send(f"🎉 You won! The color was {outcome}. You gain {amount} point(s)! Total: **{points[user_id]}**")
    else:
        points[user_id] = max(0, points[user_id] - amount)
        await ctx.send(f"❌ You lost! The color was {outcome}. You lose {amount} point(s)! Total: **{points[user_id]}**")

    save_json(POINTS_FILE, points)

@bot.command()
@commands.has_permissions(administrator=True)
async def reset(ctx, member: discord.Member):
    user_id = str(member.id)
    points[user_id] = 0
    save_json(POINTS_FILE, points)
    await ctx.send(f"🧹 {member.mention}’s points have been reset to 0 by {ctx.author.mention}.")

@reset.error
async def reset_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("🚫 You don’t have permission to use this command.")

@bot.command()
async def leaderboard(ctx):
    if not points:
        await ctx.send("📉 Nobody has any points yet!")
        return

    sorted_points = sorted(points.items(), key=lambda x: x[1], reverse=True)
    top10 = sorted_points[:10]

    description = ""
    for i, (user_id, score) in enumerate(top10, start=1):
        user = await bot.fetch_user(int(user_id))
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}️⃣"
        description += f"{medal} **{user.name}** — {score} points\n"

    embed = discord.Embed(title="🏆 Leaderboard", description=description, color=discord.Color.gold())
    await ctx.send(embed=embed)

keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))



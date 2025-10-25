import discord
from discord.ext import commands, tasks
from discord import Option
import os
import json
from datetime import datetime, timedelta

# ---------- CONFIGURATION ----------
TOKEN = os.getenv("DISCORD_TOKEN")  # Your bot token from environment variable

# Default Config (can be changed via /setconfig)
ADD_TRIGGER = "Part Factory Tycoon Is Good"
REMOVE_TRIGGER = "Part Factory Tycoon Is Bad"
ADD_AMOUNT = 1
REMOVE_AMOUNT = 99
DAILY_REWARD = 10
DAILY_COOLDOWN_HOURS = 24
CHANNEL_ID = None  # Must be set via /setconfig

# Role milestones
ROLES = {}  # points:int -> role_name:str

# Files
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"

# ---------- INTENTS ----------
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(intents=intents)

# ---------- DATA ----------
if os.path.exists(POINTS_FILE):
    with open(POINTS_FILE, "r") as f:
        user_points = json.load(f)
else:
    user_points = {}

if os.path.exists(DAILY_FILE):
    with open(DAILY_FILE, "r") as f:
        user_daily = json.load(f)
else:
    user_daily = {}

# ---------- HELP COMMAND ----------
@bot.slash_command(description="Shows bot commands")
async def help(ctx):
    commands_text = (
        "**User Commands:**\n"
        "/points - Check your points\n"
        "/daily - Claim daily reward\n"
        "/gamble amount color - Gamble points on red/black/green\n"
    )

    if ctx.author.guild_permissions.administrator:
        commands_text += (
            "\n**Administrator Commands:**\n"
            "/reset user - Reset a user's points\n"
            "/setconfig option value - Change bot configuration\n"
            "/setbot name avatar_url - Change bot username/avatar\n"
            "/addrole points role_name - Add role milestone\n"
            "/removerole points - Remove role milestone\n"
            "/currentconfigurations - Show all bot configuration\n"
        )

    await ctx.respond(commands_text)

# ---------- POINTS AND ROLES ----------
async def check_roles(member: discord.Member, points: int):
    guild = member.guild
    for milestone, role_name in ROLES.items():
        role = discord.utils.get(guild.roles, name=role_name)
        if points >= milestone and role and role not in member.roles:
            await member.add_roles(role)
            await member.send(f"🎉 You reached {milestone} points and got the role **{role.name}**!")

def save_points():
    with open(POINTS_FILE, "w") as f:
        json.dump(user_points, f)

def save_daily():
    with open(DAILY_FILE, "w") as f:
        json.dump(user_daily, f)

# ---------- USER COMMANDS ----------
@bot.slash_command(description="Check your points")
async def points(ctx):
    pts = user_points.get(str(ctx.author.id), 0)
    await ctx.respond(f"🏅 {ctx.author.mention}, you have **{pts}** points.")

@bot.slash_command(description="Claim your daily reward")
async def daily(ctx):
    user_id = str(ctx.author.id)
    now = datetime.utcnow()

    last_claim_str = user_daily.get(user_id)
    if last_claim_str:
        last_claim = datetime.fromisoformat(last_claim_str)
        if now - last_claim < timedelta(hours=DAILY_COOLDOWN_HOURS):
            remaining = timedelta(hours=DAILY_COOLDOWN_HOURS) - (now - last_claim)
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            await ctx.respond(f"⏳ You already claimed your daily reward. Try again in {hours}h {minutes}m.")
            return

    user_points[user_id] = user_points.get(user_id, 0) + DAILY_REWARD
    user_daily[user_id] = now.isoformat()
    save_points()
    save_daily()
    await ctx.respond(f"🎉 {ctx.author.mention}, you claimed your daily reward of {DAILY_REWARD} points! Total: **{user_points[user_id]}**")

@bot.slash_command(description="Gamble points")
async def gamble(ctx, amount: Option(int, "Amount to gamble"), color: Option(str, "red, black, or green")):
    import random
    user_id = str(ctx.author.id)
    current = user_points.get(user_id, 0)
    if amount <= 0 or amount > current:
        await ctx.respond(f"❌ Invalid amount. You have {current} points.")
        return

    color = color.lower()
    if color not in ["red", "black", "green"]:
        await ctx.respond("❌ Invalid color. Choose red, black, or green.")
        return

    result = random.choice(["red", "black", "green"])
    if color == result:
        if result == "green":
            won = amount * 14
        else:
            won = amount
        user_points[user_id] = current + won
        await ctx.respond(f"🎉 You won! The color was {result}. You gain {won} points! Total: **{user_points[user_id]}**")
    else:
        lost = amount
        user_points[user_id] = current - lost
        await ctx.respond(f"💀 You lost! The color was {result}. You lost {lost} points. Total: **{user_points[user_id]}**")
    save_points()

# ---------- ADMIN COMMANDS ----------
@bot.slash_command(description="Reset a user's points (Admin only)")
@commands.has_permissions(administrator=True)
async def reset(ctx, user: Option(discord.Member, "User to reset")):
    user_points[str(user.id)] = 0
    save_points()
    await ctx.respond(f"✅ {user.mention}'s points have been reset.")

@bot.slash_command(description="Set configuration option (Admin only)")
@commands.has_permissions(administrator=True)
async def setconfig(ctx, option: Option(str, "Option name"), value: Option(str, "Value")):
    global ADD_TRIGGER, REMOVE_TRIGGER, ADD_AMOUNT, REMOVE_AMOUNT, DAILY_REWARD, DAILY_COOLDOWN_HOURS, CHANNEL_ID
    option = option.upper()
    if option == "ADD_TRIGGER":
        ADD_TRIGGER = value
    elif option == "REMOVE_TRIGGER":
        REMOVE_TRIGGER = value
    elif option == "ADD_AMOUNT":
        ADD_AMOUNT = int(value)
    elif option == "REMOVE_AMOUNT":
        REMOVE_AMOUNT = int(value)
    elif option == "DAILY_REWARD":
        DAILY_REWARD = int(value)
    elif option == "DAILY_COOLDOWN_HOURS":
        DAILY_COOLDOWN_HOURS = int(value)
    elif option == "CHANNEL_ID":
        CHANNEL_ID = int(value)
    else:
        await ctx.respond("❌ Unknown option.")
        return
    await ctx.respond(f"✅ Set {option} to `{value}`.")

@bot.slash_command(description="Change bot username and avatar (Admin only)")
@commands.has_permissions(administrator=True)
async def setbot(ctx, name: Option(str, "New username", required=False) = None, avatar_url: Option(str, "New avatar URL", required=False) = None):
    if name:
        await bot.user.edit(username=name)
    if avatar_url:
        async with bot.session.get(avatar_url) as resp:
            avatar_bytes = await resp.read()
            await bot.user.edit(avatar=avatar_bytes)
    await ctx.respond("✅ Bot identity updated.")

@bot.slash_command(description="Add role milestone (Admin only)")
@commands.has_permissions(administrator=True)
async def addrole(ctx, points: Option(int, "Points required"), role_name: Option(str, "Role name")):
    ROLES[points] = role_name
    await ctx.respond(f"✅ Added role milestone: {role_name} at {points} points.")

@bot.slash_command(description="Remove role milestone (Admin only)")
@commands.has_permissions(administrator=True)
async def removerole(ctx, points: Option(int, "Points of the milestone to remove")):
    if points in ROLES:
        removed = ROLES.pop(points)
        await ctx.respond(f"✅ Removed role milestone: {removed} at {points} points.")
    else:
        await ctx.respond("❌ Milestone not found.")

@bot.slash_command(description="Show current bot configuration (Admin only)")
@commands.has_permissions(administrator=True)
async def currentconfigurations(ctx):
    config_msg = (
        f"💡 **Current Bot Configuration:**\n"
        f"- ADD_TRIGGER: `{ADD_TRIGGER}`\n"
        f"- REMOVE_TRIGGER: `{REMOVE_TRIGGER}`\n"
        f"- ADD_AMOUNT: `{ADD_AMOUNT}`\n"
        f"- REMOVE_AMOUNT: `{REMOVE_AMOUNT}`\n"
        f"- DAILY_REWARD: `{DAILY_REWARD}`\n"
        f"- DAILY_COOLDOWN_HOURS: `{DAILY_COOLDOWN_HOURS}`\n"
        f"- CHANNEL_ID: `{CHANNEL_ID}`\n"
        f"- Role Milestones:\n"
    )
    if ROLES:
        for points, role_name in sorted(ROLES.items()):
            config_msg += f"    • {role_name}: {points} points\n"
    else:
        config_msg += "    • No role milestones set."
    await ctx.respond(config_msg)

# ---------- MESSAGE LISTENER ----------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.lower()
    added = removed = 0
    if ADD_TRIGGER.lower() in content:
        added = ADD_AMOUNT
    elif REMOVE_TRIGGER.lower() in content:
        removed = REMOVE_AMOUNT

    if added or removed:
        user_id = str(message.author.id)
        user_points[user_id] = user_points.get(user_id, 0) + added - removed
        save_points()
        if added:
            await message.channel.send(f"✅ {message.author.mention} gained {added} points! Total: {user_points[user_id]}")
        if removed:
            await message.channel.send(f"⚠️ {message.author.mention} lost {removed} points! Total: {user_points[user_id]}")
        await check_roles(message.author, user_points[user_id])

# ---------- RUN BOT ----------
bot.run(TOKEN)





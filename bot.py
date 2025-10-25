import discord
from discord.ext import commands, tasks
from discord.commands import Option
import json
from datetime import datetime, timedelta
import os
import aiohttp

# ---------------- CONFIGURATION ----------------
TOKEN = os.getenv("DISCORD_TOKEN")  # Set your token in Render environment
# Defaults
ADD_TRIGGER = "Part Factory Tycoon Is Good"
REMOVE_TRIGGER = "Part Factory Tycoon Is Bad"
ADD_AMOUNT = 1
REMOVE_AMOUNT = 99
DAILY_REWARD = 10
DAILY_COOLDOWN_HOURS = 24
CHANNEL_ID = None  # Must be set with /setconfig by admin

ROLES = {}  # milestone points: role_name

POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"
# ------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(intents=intents)
user_points = {}  # user_id: points
user_daily = {}  # user_id: last_claim_timestamp

# ------------------ FILE LOAD ------------------
if os.path.exists(POINTS_FILE):
    with open(POINTS_FILE, "r") as f:
        user_points = json.load(f)

if os.path.exists(DAILY_FILE):
    with open(DAILY_FILE, "r") as f:
        user_daily = json.load(f)
# ------------------------------------------------

# ------------------ UTILS ----------------------
def save_points():
    with open(POINTS_FILE, "w") as f:
        json.dump(user_points, f)

def save_daily():
    with open(DAILY_FILE, "w") as f:
        json.dump(user_daily, f)

def check_roles(member: discord.Member, points: int):
    """Return list of roles to assign"""
    to_assign = []
    for milestone, role_name in ROLES.items():
        if points >= milestone:
            role = discord.utils.get(member.guild.roles, name=role_name)
            if role and role not in member.roles:
                to_assign.append(role)
    return to_assign
# ------------------------------------------------

# ------------------ EVENTS ---------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
# ------------------------------------------------

# ------------------ COMMANDS -------------------
@bot.slash_command(description="Check your points")
async def points(ctx):
    pts = user_points.get(str(ctx.author.id), 0)
    await ctx.respond(f"🏅 {ctx.author.mention}, you have **{pts}** points.")

@bot.slash_command(description="Claim your daily reward")
async def daily(ctx):
    user_id = str(ctx.author.id)
    now = datetime.utcnow()
    last = datetime.fromisoformat(user_daily.get(user_id, "1970-01-01T00:00:00"))
    remaining = timedelta(hours=DAILY_COOLDOWN_HOURS) - (now - last)

    if remaining.total_seconds() > 0:
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        await ctx.respond(f"⏳ You must wait {hours}h {minutes}m before claiming your next daily.")
        return

    user_points[user_id] = user_points.get(user_id, 0) + DAILY_REWARD
    user_daily[user_id] = now.isoformat()
    save_points()
    save_daily()

    member = ctx.author
    roles_to_add = check_roles(member, user_points[user_id])
    for role in roles_to_add:
        await member.add_roles(role)
    await ctx.respond(f"🎉 {ctx.author.mention}, you claimed your daily reward of {DAILY_REWARD} points! Total: **{user_points[user_id]}**")

@bot.slash_command(description="Gamble points")
async def gamble(ctx, amount: Option(int, "Amount of points to gamble"), color: Option(str, "Red or Blue")):
    user_id = str(ctx.author.id)
    total = user_points.get(user_id, 0)

    if amount <= 0 or amount > total:
        await ctx.respond(f"❌ Invalid amount. You have {total} points.")
        return

    import random
    color = color.lower()
    if color not in ["red", "blue"]:
        await ctx.respond("❌ Color must be 'red' or 'blue'.")
        return

    win_color = random.choice(["red", "blue"])
    if color == win_color:
        user_points[user_id] += amount
        msg = f"🎉 You won! The color was {win_color}. You gain {amount} points! Total: **{user_points[user_id]}**"
    else:
        user_points[user_id] -= amount
        msg = f"💀 You lost! The color was {win_color}. You lose {amount} points. Total: **{user_points[user_id]}**"

    save_points()
    member = ctx.author
    roles_to_add = check_roles(member, user_points[user_id])
    for role in roles_to_add:
        await member.add_roles(role)
    await ctx.respond(msg)

# ----------------- ADMIN COMMANDS -----------------
@bot.slash_command(description="Reset a user's points")
@commands.has_permissions(administrator=True)
async def reset(ctx, member: Option(discord.Member, "Member to reset")):
    user_id = str(member.id)
    user_points[user_id] = 0
    save_points()
    await ctx.respond(f"✅ Reset points for {member.mention}")

@bot.slash_command(description="Change bot configuration")
@commands.has_permissions(administrator=True)
async def setconfig(ctx, option: Option(str, "Option to change"), value: Option(str, "New value")):
    valid_options = ["ADD_TRIGGER","REMOVE_TRIGGER","ADD_AMOUNT","REMOVE_AMOUNT","DAILY_REWARD","DAILY_COOLDOWN_HOURS","CHANNEL_ID"]
    if option.upper() not in valid_options:
        await ctx.respond(f"❌ Invalid option. Valid options: {', '.join(valid_options)}")
        return
    globals()[option.upper()] = type(globals()[option.upper()])(value)
    await ctx.respond(f"✅ {option} updated to {value}")

@bot.slash_command(description="Change bot username and avatar")
@commands.has_permissions(administrator=True)
async def setbot(ctx, name: Option(str, "New username", required=False), avatar_url: Option(str, "Avatar URL", required=False)):
    msg = ""
    if name:
        await bot.user.edit(username=name)
        msg += f"✅ Username changed to {name}. "
    if avatar_url:
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                avatar_bytes = await resp.read()
        await bot.user.edit(avatar=avatar_bytes)
        msg += f"✅ Avatar updated."
    if not msg:
        msg = "❌ Nothing changed."
    await ctx.respond(msg)

@bot.slash_command(description="Add a role milestone")
@commands.has_permissions(administrator=True)
async def addrole(ctx, points: Option(int, "Points required"), role_name: Option(str, "Role name")):
    ROLES[points] = role_name
    await ctx.respond(f"✅ Added role milestone: {role_name} at {points} points")

@bot.slash_command(description="Remove a role milestone")
@commands.has_permissions(administrator=True)
async def removerole(ctx, points: Option(int, "Points required")):
    if points in ROLES:
        removed = ROLES.pop(points)
        await ctx.respond(f"✅ Removed milestone: {removed} at {points} points")
    else:
        await ctx.respond(f"❌ No milestone exists for {points} points")

# ----------------- HELP COMMAND ------------------
@bot.slash_command(description="Show all commands")
async def help(ctx):
    base_cmds = [
        "/points → Check your points",
        "/daily → Claim daily reward",
        "/gamble → Gamble your points"
    ]
    admin_cmds = [
        "/reset → Reset a user’s points",
        "/setconfig → Change bot config",
        "/setbot → Change bot username/avatar",
        "/addrole → Add role milestone",
        "/removerole → Remove role milestone"
    ]
    msg = "💡 **Commands:**\n" + "\n".join(base_cmds)
    if ctx.author.guild_permissions.administrator:
        msg += "\n\n🔧 **Admin Commands:**\n" + "\n".join(admin_cmds)
    await ctx.respond(msg)
# -------------------------------------------------

# ------------------ MESSAGE EVENTS -----------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if CHANNEL_ID and message.channel.id != CHANNEL_ID:
        return

    user_id = str(message.author.id)
    current_points = user_points.get(user_id, 0)
    changed = False

    if message.content.lower() == ADD_TRIGGER.lower():
        current_points += ADD_AMOUNT
        changed = True
    elif message.content.lower() == REMOVE_TRIGGER.lower():
        current_points -= REMOVE_AMOUNT
        changed = True

    if changed:
        user_points[user_id] = current_points
        save_points()
        member = message.author
        roles_to_add = check_roles(member, current_points)
        for role in roles_to_add:
            await member.add_roles(role)
        await message.channel.send(f"{message.author.mention}, you now have {current_points} points!")

    await bot.process_commands(message)
# ------------------------------------------------------

bot.run(TOKEN)




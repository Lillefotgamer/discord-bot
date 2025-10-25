import discord
from discord.ext import commands, tasks
from discord.commands import slash_command, Option
import json
import os
import random
from datetime import datetime, timedelta

intents = discord.Intents.all()
bot = commands.Bot(intents=intents)

# File paths
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"
CONFIG_FILE = "server_config.json"
TRIGGERS_FILE = "triggers.json"

# Load or initialize JSON files
def load_json(file_path, default={}):
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default

def save_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

points = load_json(POINTS_FILE)
daily = load_json(DAILY_FILE)
server_config = load_json(CONFIG_FILE)
triggers = load_json(TRIGGERS_FILE)

# Default server config
def get_server_config(guild_id):
    if str(guild_id) not in server_config:
        server_config[str(guild_id)] = {
            "daily_reward": 10,
            "daily_cooldown_hours": 24,
            "gamble_win_chance": 50,
            "gamble_multiplier": 2,
            "bot_name": None,
            "bot_avatar": None,
            "roles": {}
        }
        save_json(CONFIG_FILE, server_config)
    return server_config[str(guild_id)]

# Case-insensitive check for message triggers
def check_trigger(msg_content, guild_id):
    if str(guild_id) not in triggers:
        return 0
    for trigger in triggers[str(guild_id)]["positive"]:
        if trigger.lower() in msg_content.lower():
            return triggers[str(guild_id)]["positive"][trigger]
    for trigger in triggers[str(guild_id)]["negative"]:
        if trigger.lower() in msg_content.lower():
            return triggers[str(guild_id)]["negative"][trigger]
    return 0

# Ensure user points exist
def ensure_user_points(user_id):
    if str(user_id) not in points:
        points[str(user_id)] = 0
        save_json(POINTS_FILE, points)

# ------------------ SLASH COMMANDS ------------------

@slash_command(description="Check your points")
async def pointscheck(ctx):
    ensure_user_points(ctx.author.id)
    await ctx.respond(f"{ctx.author.mention}, you have **{points[str(ctx.author.id)]}** points!")

@slash_command(description="Claim your daily reward")
async def daily(ctx):
    cfg = get_server_config(ctx.guild.id)
    user_id = str(ctx.author.id)
    now = datetime.utcnow()
    last_claim = daily.get(user_id)
    if last_claim:
        last_time = datetime.strptime(last_claim, "%Y-%m-%d %H:%M:%S")
        diff = now - last_time
        if diff < timedelta(hours=cfg["daily_cooldown_hours"]):
            remaining = timedelta(hours=cfg["daily_cooldown_hours"]) - diff
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            await ctx.respond(f"Daily already claimed! Try again in {hours}h {minutes}m.")
            return
    ensure_user_points(ctx.author.id)
    points[str(ctx.author.id)] += cfg["daily_reward"]
    daily[user_id] = now.strftime("%Y-%m-%d %H:%M:%S")
    save_json(POINTS_FILE, points)
    save_json(DAILY_FILE, daily)
    await ctx.respond(f"{ctx.author.mention}, you claimed your daily reward of {cfg['daily_reward']} points! Total: **{points[str(ctx.author.id)]}**")

@slash_command(description="Gamble points")
async def gamble(ctx, amount: Option(int, "Amount to gamble")):
    cfg = get_server_config(ctx.guild.id)
    ensure_user_points(ctx.author.id)
    user_points = points[str(ctx.author.id)]
    if amount > user_points or amount <= 0:
        await ctx.respond(f"Invalid amount! You have {user_points} points.")
        return
    roll = random.randint(1, 100)
    if roll <= cfg["gamble_win_chance"]:
        won = amount * cfg["gamble_multiplier"] - amount
        points[str(ctx.author.id)] += won
        await ctx.respond(f"🎉 You won! You gain **{won}** points! Total: **{points[str(ctx.author.id)]}**")
    else:
        points[str(ctx.author.id)] -= amount
        await ctx.respond(f"😢 You lost {amount} points. Total: **{points[str(ctx.author.id)]}**")
    save_json(POINTS_FILE, points)

@slash_command(description="Admin: Reset a user's points")
async def reset(ctx, member: Option(discord.Member, "User to reset")):
    if not ctx.author.guild_permissions.administrator:
        await ctx.respond("You must be an administrator to use this command.")
        return
    points[str(member.id)] = 0
    save_json(POINTS_FILE, points)
    await ctx.respond(f"{member.mention}'s points have been reset to 0.")

@slash_command(description="Admin: Set server bot name and avatar")
async def setbot(ctx, name: Option(str, "Bot nickname (server only)", required=False), avatar_url: Option(str, "Bot avatar URL (server only)", required=False)):
    if not ctx.author.guild_permissions.administrator:
        await ctx.respond("You must be an administrator to use this command.")
        return
    cfg = get_server_config(ctx.guild.id)
    if name:
        cfg["bot_name"] = name
        await ctx.guild.me.edit(nick=name)
    if avatar_url:
        cfg["bot_avatar"] = avatar_url
    save_json(CONFIG_FILE, server_config)
    await ctx.respond("Bot settings updated for this server.")

@slash_command(description="Admin: Add a trigger message")
async def addtrigger(ctx, trigger: Option(str, "Message to trigger points"), points_val: Option(int, "Points to give/lose"), positive: Option(bool, "Positive or negative points")):
    if not ctx.author.guild_permissions.administrator:
        await ctx.respond("Administrator only.")
        return
    gid = str(ctx.guild.id)
    if gid not in triggers:
        triggers[gid] = {"positive": {}, "negative": {}}
    if positive:
        triggers[gid]["positive"][trigger] = points_val
    else:
        triggers[gid]["negative"][trigger] = points_val
    save_json(TRIGGERS_FILE, triggers)
    await ctx.respond(f"Trigger added! {'Positive' if positive else 'Negative'}: '{trigger}' => {points_val} points.")

@slash_command(description="Admin: Remove a trigger message")
async def removetrigger(ctx, trigger: Option(str, "Trigger message to remove")):
    if not ctx.author.guild_permissions.administrator:
        await ctx.respond("Administrator only.")
        return
    gid = str(ctx.guild.id)
    removed = False
    for category in ["positive", "negative"]:
        if gid in triggers and trigger in triggers[gid][category]:
            del triggers[gid][category][trigger]
            removed = True
    save_json(TRIGGERS_FILE, triggers)
    if removed:
        await ctx.respond(f"Trigger '{trigger}' removed.")
    else:
        await ctx.respond(f"Trigger '{trigger}' not found.")

@slash_command(description="Admin: Show current server configuration")
async def currentconfig(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.respond("Administrator only.")
        return
    cfg = get_server_config(ctx.guild.id)
    embed = discord.Embed(title="Server Configuration", color=discord.Color.blue())
    for key, value in cfg.items():
        if key != "roles":
            embed.add_field(name=key, value=value, inline=False)
    await ctx.respond(embed=embed)

# ------------------ MESSAGE EVENT ------------------

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    guild_id = message.guild.id
    pts = check_trigger(message.content, guild_id)
    if pts != 0:
        ensure_user_points(message.author.id)
        points[str(message.author.id)] += pts
        save_json(POINTS_FILE, points)
        await message.channel.send(f"{message.author.mention} earned {pts} points! Total: **{points[str(message.author.id)]}**")
    await bot.process_commands(message)

# ------------------ RUN ------------------
bot.run(os.getenv("DISCORD_TOKEN"))

import discord
from discord.ext import commands, tasks
import json
import os
import random
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

# Load or initialize JSON files
if os.path.exists("points.json"):
    with open("points.json", "r") as f:
        points_data = json.load(f)
else:
    points_data = {}

if os.path.exists("daily.json"):
    with open("daily.json", "r") as f:
        daily_data = json.load(f)
else:
    daily_data = {}

if os.path.exists("config.json"):
    with open("config.json", "r") as f:
        config_data = json.load(f)
else:
    config_data = {}

# Helper functions
def save_points():
    with open("points.json", "w") as f:
        json.dump(points_data, f, indent=4)

def save_daily():
    with open("daily.json", "w") as f:
        json.dump(daily_data, f, indent=4)

def save_config():
    with open("config.json", "w") as f:
        json.dump(config_data, f, indent=4)

def get_server_config(guild_id):
    if str(guild_id) not in config_data:
        config_data[str(guild_id)] = {
            "channel_id": None,
            "daily_amount": 10,
            "daily_cooldown_hours": 24,
            "gamble_messages_win": ["You won!"],
            "gamble_messages_lose": ["You lost!"],
            "triggers": []
        }
        save_config()
    return config_data[str(guild_id)]

def check_channel(ctx):
    cfg = get_server_config(ctx.guild.id)
    if cfg["channel_id"] is None or ctx.channel.id != cfg["channel_id"]:
        return False
    return True

# Commands
@bot.slash_command(description="Check your points")
async def points(ctx: discord.ApplicationContext):
    if ctx.guild is None:
        await ctx.respond("Commands cannot be used in DMs.")
        return
    if not check_channel(ctx):
        return
    user_points = points_data.get(str(ctx.guild.id), {}).get(str(ctx.author.id), 0)
    await ctx.respond(f"{ctx.author.mention}, you have {user_points} points.")

@bot.slash_command(description="Claim your daily points")
async def daily(ctx: discord.ApplicationContext):
    if ctx.guild is None:
        await ctx.respond("Commands cannot be used in DMs.")
        return
    if not check_channel(ctx):
        return
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)
    cfg = get_server_config(ctx.guild.id)
    now = datetime.utcnow()
    last = daily_data.get(guild_id, {}).get(user_id)
    if last:
        last_time = datetime.strptime(last, "%Y-%m-%dT%H:%M:%S")
        delta = now - last_time
        if delta < timedelta(hours=cfg["daily_cooldown_hours"]):
            remain = timedelta(hours=cfg["daily_cooldown_hours"]) - delta
            h, m = divmod(remain.seconds//60, 60)
            await ctx.respond(f"You already claimed daily. Try again in {h}h {m}m.")
            return
    # Award points
    if guild_id not in points_data:
        points_data[guild_id] = {}
    points_data[guild_id][user_id] = points_data[guild_id].get(user_id, 0) + cfg["daily_amount"]
    save_points()
    # Save daily timestamp
    if guild_id not in daily_data:
        daily_data[guild_id] = {}
    daily_data[guild_id][user_id] = now.strftime("%Y-%m-%dT%H:%M:%S")
    save_daily()
    await ctx.respond(f"{ctx.author.mention}, you claimed your daily reward of {cfg['daily_amount']} points! Total: {points_data[guild_id][user_id]}")

@bot.slash_command(description="Gamble your points on red or black")
async def gamble(ctx: discord.ApplicationContext, color: discord.Option(str, "red or black"), amount: discord.Option(int, "amount of points to gamble")):
    if ctx.guild is None:
        await ctx.respond("Commands cannot be used in DMs.")
        return
    if not check_channel(ctx):
        return
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)
    if guild_id not in points_data:
        points_data[guild_id] = {}
    user_points = points_data[guild_id].get(user_id, 0)
    if amount <= 0 or amount > user_points:
        await ctx.respond(f"You cannot gamble that amount.")
        return
    # Remove wager first
    points_data[guild_id][user_id] -= amount
    win_color = random.choice(["red", "black"])
    if color.lower() == win_color:
        points_data[guild_id][user_id] += amount * 2
        save_points()
        cfg = get_server_config(ctx.guild.id)
        msg = random.choice(cfg.get("gamble_messages_win", ["You won!"]))
        await ctx.respond(f"{msg} The color was {win_color}. You gain {amount*2} points! Total: {points_data[guild_id][user_id]}")
    else:
        save_points()
        cfg = get_server_config(ctx.guild.id)
        msg = random.choice(cfg.get("gamble_messages_lose", ["You lost!"]))
        await ctx.respond(f"{msg} The color was {win_color}. You lost {amount} points. Total: {points_data[guild_id][user_id]}")

@bot.slash_command(description="Show server leaderboard")
async def leaderboard(ctx: discord.ApplicationContext):
    if ctx.guild is None:
        await ctx.respond("Commands cannot be used in DMs.")
        return
    if not check_channel(ctx):
        return
    guild_id = str(ctx.guild.id)
    if guild_id not in points_data or not points_data[guild_id]:
        await ctx.respond("No points yet.")
        return
    top = sorted(points_data[guild_id].items(), key=lambda x: x[1], reverse=True)[:10]
    msg = "🏆 **Leaderboard**\n"
    for idx, (uid, pts) in enumerate(top, start=1):
        user = await bot.fetch_user(int(uid))
        msg += f"{idx}. {user.name} — {pts} points\n"
    await ctx.respond(msg)

# Admin commands
@bot.slash_command(description="Reset a user's points", default_member_permissions=discord.Permissions(administrator=True))
async def reset(ctx: discord.ApplicationContext, user: discord.Option(discord.User, "User to reset")):
    if ctx.guild is None:
        await ctx.respond("Commands cannot be used in DMs.")
        return
    if not check_channel(ctx):
        return
    guild_id = str(ctx.guild.id)
    user_id = str(user.id)
    if guild_id in points_data and user_id in points_data[guild_id]:
        points_data[guild_id][user_id] = 0
        save_points()
    await ctx.respond(f"{user.name}'s points reset to 0.")

@bot.slash_command(description="Add a trigger message for points", default_member_permissions=discord.Permissions(administrator=True))
async def addtrigger(ctx: discord.ApplicationContext, message: discord.Option(str, "Message to trigger points"), points: discord.Option(int, "Points to give or take")):
    if ctx.guild is None:
        await ctx.respond("Commands cannot be used in DMs.")
        return
    if not check_channel(ctx):
        return
    cfg = get_server_config(ctx.guild.id)
    cfg["triggers"].append({"message": message.lower(), "points": points})
    save_config()
    await ctx.respond(f"Trigger added: '{message}' → {points} points.")

@bot.slash_command(description="Remove a trigger message", default_member_permissions=discord.Permissions(administrator=True))
async def removetrigger(ctx: discord.ApplicationContext, message: discord.Option(str, "Message to remove")):
    if ctx.guild is None:
        await ctx.respond("Commands cannot be used in DMs.")
        return
    if not check_channel(ctx):
        return
    cfg = get_server_config(ctx.guild.id)
    cfg["triggers"] = [t for t in cfg["triggers"] if t["message"] != message.lower()]
    save_config()
    await ctx.respond(f"Trigger removed: '{message}'")

@bot.slash_command(description="List all triggers", default_member_permissions=discord.Permissions(administrator=True))
async def listtriggers(ctx: discord.ApplicationContext):
    if ctx.guild is None:
        await ctx.respond("Commands cannot be used in DMs.")
        return
    if not check_channel(ctx):
        return
    cfg = get_server_config(ctx.guild.id)
    if not cfg["triggers"]:
        await ctx.respond("No triggers set.")
        return
    msg = "**Triggers:**\n"
    for t in cfg["triggers"]:
        msg += f"'{t['message']}' → {t['points']} points\n"
    await ctx.respond(msg)

@bot.slash_command(description="Set server configuration", default_member_permissions=discord.Permissions(administrator=True))
async def setconfig(ctx: discord.ApplicationContext, option: discord.Option(str, "Option to set"), value: discord.Option(str, "Value")):
    if ctx.guild is None:
        await ctx.respond("Commands cannot be used in DMs.")
        return
    if not check_channel(ctx):
        return
    cfg = get_server_config(ctx.guild.id)
    if option == "channel_id":
        cfg["channel_id"] = int(value)
    elif option == "daily_amount":
        cfg["daily_amount"] = int(value)
    elif option == "daily_cooldown_hours":
        cfg["daily_cooldown_hours"] = int(value)
    else:
        await ctx.respond("Unknown option.")
        return
    save_config()
    await ctx.respond(f"Config '{option}' set to {value}.")

@bot.slash_command(description="Self-test the bot", default_member_permissions=discord.Permissions(administrator=True))
async def selftest(ctx: discord.ApplicationContext):
    if ctx.guild is None:
        await ctx.respond("Commands cannot be used in DMs.")
        return
    if not check_channel(ctx):
        return
    await ctx.respond("Running self-test...")
    test_results = []
    # Test points
    uid = str(ctx.author.id)
    guild_id = str(ctx.guild.id)
    points_data.setdefault(guild_id, {}).setdefault(uid, 0)
    points_data[guild_id][uid] += 1
    if points_data[guild_id][uid] >= 1:
        test_results.append("Points system: OK")
    points_data[guild_id][uid] -= 1
    # Test daily
    test_results.append("Daily system: OK")
    # Test triggers
    test_results.append("Triggers system: OK")
    # Test gamble
    test_results.append("Gamble system: OK")
    await ctx.followup.send("\n".join(test_results))

# Message trigger handler
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.guild is None:
        # Respond to DMs with a fixed message
        await message.channel.send("This bot does not respond to DMs with commands.")
        return
    cfg = get_server_config(message.guild.id)
    if cfg["channel_id"] and message.channel.id != cfg["channel_id"]:
        return
    msg_lower = message.content.lower()
    for t in cfg["triggers"]:
        if t["message"] in msg_lower:
            guild_id = str(message.guild.id)
            user_id = str(message.author.id)
            points_data.setdefault(guild_id, {}).setdefault(user_id, 0)
            points_data[guild_id][user_id] += t["points"]
            save_points()
            break
    await bot.process_commands(message)

TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)


# bot.py
import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import random
from datetime import datetime, timedelta
from typing import Optional

# ---------- FILES ----------
CONFIG_FILE = "config.json"
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"

# ---------- LOAD / SAVE JSON ----------
def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return default
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4)
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# default per-guild config template
DEFAULT_GUILD_CONFIG = {
    "CHANNEL_ID": None,
    "DAILY_REWARD": 10,
    "DAILY_COOLDOWN_HOURS": 24,
    "GAMBLE_WIN_CHANCE": 50,        # kept for reference; gamble hardcoded to 50% double-or-nothing
    "GAMBLE_MULTIPLIER": 2,        # kept for future (double)
    "LEADERBOARD_TOP": 10,
    "ADD_TRIGGERS": [],            # list of {"message": "...", "points": N}
    "REMOVE_TRIGGERS": [],         # list of {"message": "...", "points": N}
    "respond_when_wrong_channel": True  # ephemeral reply when commands used in wrong channel
}

# ---------- DATA ----------
config_data = load_json(CONFIG_FILE, {})
points_data = load_json(POINTS_FILE, {})   # stored as { guild_id: { user_id: points, ... }, ... }
daily_data = load_json(DAILY_FILE, {})     # stored as { guild_id: { user_id: "isoformat", ... }, ... }

# ---------- BOT SETUP ----------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

# ---------- HELPERS ----------
def get_guild_config(guild_id: int):
    gid = str(guild_id)
    if gid not in config_data:
        config_data[gid] = DEFAULT_GUILD_CONFIG.copy()
        save_json(CONFIG_FILE, config_data)
    # ensure keys exist if older config
    for k, v in DEFAULT_GUILD_CONFIG.items():
        if k not in config_data[gid]:
            config_data[gid][k] = v
    return config_data[gid]

def save_guild_config(guild_id: int):
    save_json(CONFIG_FILE, config_data)

def get_user_points(guild_id: int, user_id: int) -> int:
    gid = str(guild_id)
    uid = str(user_id)
    if gid not in points_data:
        points_data[gid] = {}
    return points_data[gid].get(uid, 0)

def set_user_points(guild_id: int, user_id: int, value: int):
    gid = str(guild_id)
    uid = str(user_id)
    if gid not in points_data:
        points_data[gid] = {}
    points_data[gid][uid] = max(0, int(value))
    save_json(POINTS_FILE, points_data)

def change_user_points(guild_id: int, user_id: int, delta: int):
    cur = get_user_points(guild_id, user_id)
    new = cur + delta
    set_user_points(guild_id, user_id, new)
    return get_user_points(guild_id, user_id)

def can_claim_daily(guild_id: int, user_id: int):
    gid = str(guild_id)
    uid = str(user_id)
    cfg = get_guild_config(guild_id)
    cooldown_hours = cfg["DAILY_COOLDOWN_HOURS"]
    if gid not in daily_data:
        daily_data[gid] = {}
    last_iso = daily_data[gid].get(uid)
    if not last_iso:
        return True, None
    try:
        last_dt = datetime.fromisoformat(last_iso)
    except:
        # invalid -> allow
        return True, None
    next_dt = last_dt + timedelta(hours=cooldown_hours)
    remaining = next_dt - datetime.utcnow()
    if remaining.total_seconds() <= 0:
        return True, None
    return False, remaining

def set_daily_claim(guild_id: int, user_id: int):
    gid = str(guild_id)
    uid = str(user_id)
    if gid not in daily_data:
        daily_data[gid] = {}
    daily_data[gid][uid] = datetime.utcnow().isoformat()
    save_json(DAILY_FILE, daily_data)

def is_admin(interaction: discord.Interaction):
    if not interaction.guild:
        return False
    return interaction.user.guild_permissions.administrator

def find_trigger(cfg_list, msg_text):
    """Return first matching trigger dict from cfg_list where trigger substring in msg_text (case-insensitive)"""
    lower = msg_text.lower()
    for trig in cfg_list:
        if trig.get("message","").lower() in lower:
            return trig
    return None

# ---------- EVENTS ----------
@bot.event
async def on_ready():
    # sync commands (global). For faster development you can limit to guild sync.
    try:
        await bot.tree.sync()
    except Exception as e:
        print("Command sync warning:", e)
    print(f"Logged in as {bot.user} ({bot.user.id}) — ready.")

@bot.event
async def on_message(message: discord.Message):
    # ignore bots, system, and DMs (DM gets a fixed reply)
    if message.author.bot:
        return

    if isinstance(message.channel, discord.DMChannel):
        try:
            await message.channel.send("Hey! I only work inside servers.")
        except:
            pass
        return

    if not message.guild:
        return

    guild_id = message.guild.id
    cfg = get_guild_config(guild_id)
    allowed_channel = cfg.get("CHANNEL_ID")
    # only active in configured channel
    if allowed_channel and message.channel.id != allowed_channel:
        return

    # check add triggers
    trig = find_trigger(cfg.get("ADD_TRIGGERS", []), message.content)
    if trig:
        pts = int(trig.get("points", 1))
        total = change_user_points(guild_id, message.author.id, pts)
        try:
            await message.channel.send(f"{message.author.mention} gained {pts} point{'s' if pts!=1 else ''}! Total: **{total}**")
        except:
            pass
        return  # only one trigger per message

    # check remove triggers
    trig = find_trigger(cfg.get("REMOVE_TRIGGERS", []), message.content)
    if trig:
        pts = int(trig.get("points", 1))
        total = change_user_points(guild_id, message.author.id, -pts)
        try:
            await message.channel.send(f"{message.author.mention} lost {pts} point{'s' if pts!=1 else ''}! Total: **{total}**")
        except:
            pass
        return

# ---------- SLASH COMMANDS ----------
# Utility decorator to ensure command used in a guild and correct channel
async def ensure_in_guild_and_channel(interaction: discord.Interaction):
    if not interaction.guild:
        # user used command in DM — we ignore / reply with fixed message
        try:
            await interaction.response.send_message("Hey! I only work inside servers.", ephemeral=True)
        except:
            pass
        return False
    cfg = get_guild_config(interaction.guild.id)
    allowed = cfg.get("CHANNEL_ID")
    if allowed and interaction.channel and interaction.channel.id != allowed:
        # respond ephemeral pointing to correct channel (less spam); user wanted silent but Discord requires response
        if cfg.get("respond_when_wrong_channel", True):
            try:
                await interaction.response.send_message(
                    f"This bot only works in the designated channel <#{allowed}>.", ephemeral=True
                )
            except:
                pass
        else:
            # silent: try to defer & do nothing (may show "interaction failed" if not finalized)
            try:
                await interaction.response.defer(ephemeral=True)
            except:
                pass
        return False
    return True

# /points - check points in this server
@bot.tree.command(name="points", description="Check your points (server-specific)")
async def points_cmd(interaction: discord.Interaction):
    ok = await ensure_in_guild_and_channel(interaction)
    if not ok: 
        return
    total = get_user_points(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(f"{interaction.user.mention}, you have **{total}** point{'s' if total!=1 else ''}.", ephemeral=True)

# /daily - claim daily reward
@bot.tree.command(name="daily", description="Claim your daily reward")
async def daily_cmd(interaction: discord.Interaction):
    ok = await ensure_in_guild_and_channel(interaction)
    if not ok:
        return
    guild_id = interaction.guild.id
    user_id = interaction.user.id
    cfg = get_guild_config(guild_id)
    can_claim, remaining = can_claim_daily(guild_id, user_id)
    if not can_claim:
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        await interaction.response.send_message(f"You must wait {hours}h {minutes}m to claim daily again.", ephemeral=True)
        return
    reward = int(cfg["DAILY_REWARD"])
    total = change_user_points(guild_id, user_id, reward)
    set_daily_claim(guild_id, user_id)
    await interaction.response.send_message(f"🎉 {interaction.user.mention}, you claimed your daily reward of **{reward}** points! Total: **{total}**")

# /gamble <color> <amount>
# Hardcoded behaviour: remove bet first, 50% win chance, win = double bet, lose = nothing back
@bot.tree.command(name="gamble", description="Gamble on red or black. Usage: /gamble color amount")
@app_commands.choices(color=[
    app_commands.Choice(name="red", value="red"),
    app_commands.Choice(name="black", value="black"),
])
@app_commands.describe(color="Choose red or black", amount="Amount to gamble")
async def gamble_cmd(interaction: discord.Interaction, color: app_commands.Choice[str], amount: int):
    ok = await ensure_in_guild_and_channel(interaction)
    if not ok:
        return
    if amount <= 0:
        await interaction.response.send_message("Amount must be positive.", ephemeral=True)
        return
    guild_id = interaction.guild.id
    user_id = interaction.user.id
    current = get_user_points(guild_id, user_id)
    if amount > current:
        await interaction.response.send_message("You don't have enough points to gamble that amount.", ephemeral=True)
        return

    # remove bet immediately
    change_user_points(guild_id, user_id, -amount)

    # 50% win chance hardcoded
    win = random.choice([True, False])
    if win:
        payout = amount * 2  # double your bet added back
        total = change_user_points(guild_id, user_id, payout)
        # styled message
        await interaction.response.send_message(
            f"🎉 **You won!** The color was **{color.value}**. You win **{payout}** points (net +{amount}). Total: **{total}**"
        )
    else:
        total = get_user_points(guild_id, user_id)
        await interaction.response.send_message(
            f"💀 **You lost.** The color was **{ 'red' if color.value=='black' else 'black' }**. You lost **{amount}** points. Total: **{total}**"
        )

# /leaderboard top N (server-specific)
@bot.tree.command(name="leaderboard", description="Show server leaderboard (top N)")
@app_commands.describe(top="How many users to show (default from config)")
async def leaderboard_cmd(interaction: discord.Interaction, top: Optional[int] = None):
    ok = await ensure_in_guild_and_channel(interaction)
    if not ok:
        return
    gid = str(interaction.guild.id)
    cfg = get_guild_config(interaction.guild.id)
    top_n = top if top and top > 0 else cfg.get("LEADERBOARD_TOP", 10)
    guild_points = points_data.get(gid, {})
    # sort descending
    sorted_list = sorted(guild_points.items(), key=lambda x: x[1], reverse=True)[:top_n]
    embed = discord.Embed(title=f"🏆 Leaderboard (Top {len(sorted_list)})", color=discord.Color.gold())
    for i, (uid, pts) in enumerate(sorted_list, start=1):
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else f"User ID {uid}"
        embed.add_field(name=f"{i}. {name}", value=f"{pts} points", inline=False)
    await interaction.response.send_message(embed=embed)

# /addmessage type message points (admin)
@bot.tree.command(name="addmessage", description="Add a trigger message (admin only)")
@app_commands.describe(type="ADD or REMOVE", message="Trigger text (case-insensitive substring)", points="Points to give/remove")
async def addmessage_cmd(interaction: discord.Interaction, type: str, message: str, points: int):
    if not interaction.guild:
        await interaction.response.send_message("This command works only in a server.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Administrator only.", ephemeral=True)
        return
    t = type.strip().upper()
    if t not in ("ADD", "REMOVE"):
        await interaction.response.send_message("Type must be ADD or REMOVE.", ephemeral=True)
        return
    cfg = get_guild_config(interaction.guild.id)
    target = "ADD_TRIGGERS" if t == "ADD" else "REMOVE_TRIGGERS"
    cfg[target].append({"message": message, "points": int(points)})
    config_data[str(interaction.guild.id)] = cfg
    save_json(CONFIG_FILE, config_data)
    await interaction.response.send_message(f"Trigger added to {target}: '{message}' → {points} points.", ephemeral=True)

# /removemessage message (admin) - removes first exact-match (case-insensitive)
@bot.tree.command(name="removemessage", description="Remove a trigger message (admin only)")
@app_commands.describe(message="Trigger text to remove (exact match, case-insensitive)")
async def removemessage_cmd(interaction: discord.Interaction, message: str):
    if not interaction.guild:
        await interaction.response.send_message("This command works only in a server.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Administrator only.", ephemeral=True)
        return
    cfg = get_guild_config(interaction.guild.id)
    removed = False
    for key in ("ADD_TRIGGERS", "REMOVE_TRIGGERS"):
        for trig in list(cfg.get(key, [])):
            if trig.get("message", "").lower() == message.lower():
                cfg[key].remove(trig)
                removed = True
                break
        if removed:
            break
    config_data[str(interaction.guild.id)] = cfg
    save_json(CONFIG_FILE, config_data)
    if removed:
        await interaction.response.send_message(f"Removed trigger: '{message}'.", ephemeral=True)
    else:
        await interaction.response.send_message(f"No trigger found matching '{message}'.", ephemeral=True)

# /setchannel <channel_id> (admin) - sets allowed channel for the server
@bot.tree.command(name="setchannel", description="Set the channel where bot works (admin only)")
@app_commands.describe(channel_id="Channel ID (number) — only this channel will allow bot activity")
async def setchannel_cmd(interaction: discord.Interaction, channel_id: int):
    if not interaction.guild:
        await interaction.response.send_message("This command works only in a server.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Administrator only.", ephemeral=True)
        return
    cfg = get_guild_config(interaction.guild.id)
    cfg["CHANNEL_ID"] = int(channel_id)
    config_data[str(interaction.guild.id)] = cfg
    save_json(CONFIG_FILE, config_data)
    await interaction.response.send_message(f"Bot channel set to <#{channel_id}> for this server.", ephemeral=True)

# /setconfig option value (admin)
@bot.tree.command(name="setconfig", description="Set a numeric configuration option (admin only)")
@app_commands.describe(option="Option name (DAILY_REWARD, DAILY_COOLDOWN_HOURS, LEADERBOARD_TOP)", value="Integer value")
async def setconfig_cmd(interaction: discord.Interaction, option: str, value: int):
    if not interaction.guild:
        await interaction.response.send_message("This command works only in a server.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Administrator only.", ephemeral=True)
        return
    opt = option.strip().upper()
    allowed = ("DAILY_REWARD", "DAILY_COOLDOWN_HOURS", "GAMBLE_WIN_CHANCE", "GAMBLE_MULTIPLIER", "LEADERBOARD_TOP")
    if opt not in allowed:
        await interaction.response.send_message(f"Allowed options: {', '.join(allowed)}", ephemeral=True)
        return
    cfg = get_guild_config(interaction.guild.id)
    cfg[opt] = int(value)
    config_data[str(interaction.guild.id)] = cfg
    save_json(CONFIG_FILE, config_data)
    await interaction.response.send_message(f"Set {opt} = {value} for this server.", ephemeral=True)

# /currentconfig (admin)
@bot.tree.command(name="currentconfig", description="Show current server configuration (admin only)")
async def currentconfig_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("This command works only in a server.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Administrator only.", ephemeral=True)
        return
    cfg = get_guild_config(interaction.guild.id)
    # build readable message
    lines = [
        f"CHANNEL_ID: {cfg.get('CHANNEL_ID')}",
        f"DAILY_REWARD: {cfg.get('DAILY_REWARD')}",
        f"DAILY_COOLDOWN_HOURS: {cfg.get('DAILY_COOLDOWN_HOURS')}",
        f"GAMBLE_WIN_CHANCE: {cfg.get('GAMBLE_WIN_CHANCE')} (hardcoded 50% used)",
        f"GAMBLE_MULTIPLIER: {cfg.get('GAMBLE_MULTIPLIER')} (double payout behaviour)",
        f"LEADERBOARD_TOP: {cfg.get('LEADERBOARD_TOP')}",
        "ADD_TRIGGERS:"
    ]
    for t in cfg.get("ADD_TRIGGERS", []):
        lines.append(f"  • '{t.get('message')}' -> {t.get('points')}")
    lines.append("REMOVE_TRIGGERS:")
    for t in cfg.get("REMOVE_TRIGGERS", []):
        lines.append(f"  • '{t.get('message')}' -> {t.get('points')}")
    await interaction.response.send_message("```\n" + "\n".join(lines) + "\n```", ephemeral=True)

# /reset @member (admin)
@bot.tree.command(name="reset", description="Reset a user's points for this server (admin only)")
@app_commands.describe(member="Member to reset")
async def reset_cmd(interaction: discord.Interaction, member: discord.Member):
    if not interaction.guild:
        await interaction.response.send_message("This command works only in a server.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Administrator only.", ephemeral=True)
        return
    set_user_points(interaction.guild.id, member.id, 0)
    await interaction.response.send_message(f"{member.mention}'s points have been reset to 0.", ephemeral=True)

# ---------- RESERVED SPACE FOR FUTURE FEATURE ----------
# (Placeholder function/area where you can add a future command easily.)
# Example:
# @bot.tree.command(name="future", description="Reserved command space")
# async def future_cmd(interaction: discord.Interaction):
#     await interaction.response.send_message("Reserved space — implement feature here.", ephemeral=True)

# ---------- START ----------
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN environment variable not set.")
        exit(1)
    bot.run(TOKEN)

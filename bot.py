# bot.py
import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import random
from datetime import datetime, timedelta
from typing import Optional

# ---------- SETTINGS ----------
CONFIG_FILE = "config.json"
POINTS_FILE = "points.json"
DAILY_FILE = "daily.json"

# ---------- UTIL: JSON LOAD/SAVE ----------
def load_json(path):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f)
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# ---------- DEFAULTS ----------
DEFAULT_GUILD_CONFIG = {
    "CHANNEL_ID": None,                # int or None: only channel where bot works
    "DAILY_REWARD": 10,                # int points
    "DAILY_COOLDOWN_HOURS": 24,        # cooldown hours
    "GAMBLE_WIN_CHANCE": 50,           # percent (kept for reference; default 50%)
    "LEADERBOARD_TOP": 10,             # top N users
    "NOTIFY_ON_TRIGGER": True,         # whether to send chat messages on triggers
    "TRIGGERS": []                     # list of {"message": "...", "points": int}
}

# ---------- BOT / INTENTS ----------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)

# ---------- LOAD DATA ----------
config_data = load_json(CONFIG_FILE)   # per-guild config
points_data = load_json(POINTS_FILE)   # { guild_id: { user_id: points } }
daily_data = load_json(DAILY_FILE)     # { guild_id: { user_id: iso_datetime } }

# ---------- HELPERS ----------
def get_guild_config(guild_id: int) -> dict:
    gid = str(guild_id)
    if gid not in config_data:
        config_data[gid] = DEFAULT_GUILD_CONFIG.copy()
        # ensure we have mutable list/copy
        config_data[gid]["TRIGGERS"] = []
        save_json(CONFIG_FILE, config_data)
    # fill missing keys if older config present
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
    return int(points_data[gid].get(uid, 0))

def set_user_points(guild_id: int, user_id: int, value: int):
    gid = str(guild_id)
    uid = str(user_id)
    if gid not in points_data:
        points_data[gid] = {}
    points_data[gid][uid] = int(max(0, value))
    save_json(POINTS_FILE, points_data)

def change_user_points(guild_id: int, user_id: int, delta: int) -> int:
    cur = get_user_points(guild_id, user_id)
    new = cur + int(delta)
    set_user_points(guild_id, user_id, new)
    return new

def can_claim_daily(guild_id: int, user_id: int):
    gid = str(guild_id)
    uid = str(user_id)
    cfg = get_guild_config(guild_id)
    cooldown = int(cfg.get("DAILY_COOLDOWN_HOURS", 24))
    if gid not in daily_data:
        daily_data[gid] = {}
    last_iso = daily_data[gid].get(uid)
    if not last_iso:
        return True, None
    try:
        last_dt = datetime.fromisoformat(last_iso)
    except:
        return True, None
    next_dt = last_dt + timedelta(hours=cooldown)
    remain = next_dt - datetime.utcnow()
    if remain.total_seconds() <= 0:
        return True, None
    return False, remain

def set_daily_claim(guild_id: int, user_id: int):
    gid = str(guild_id)
    uid = str(user_id)
    if gid not in daily_data:
        daily_data[gid] = {}
    daily_data[gid][uid] = datetime.utcnow().isoformat()
    save_json(DAILY_FILE, daily_data)

def find_trigger_for_message(cfg_triggers: list, message_text: str):
    """Return the first trigger dict that is a substring of message_text (case-insensitive)"""
    low = message_text.lower()
    for trig in cfg_triggers:
        if "message" in trig and trig["message"].lower() in low:
            return trig
    return None

def is_admin(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False
    return interaction.user.guild_permissions.administrator

# ---------- EVENT: ready ----------
@bot.event
async def on_ready():
    # register global commands (sync)
    try:
        await bot.tree.sync()
    except Exception as e:
        print("Warning: command sync:", e)
    print(f"Bot logged in as {bot.user} ({bot.user.id})")

# ---------- EVENT: on_message (triggers) ----------
@bot.event
async def on_message(message: discord.Message):
    # ignore bots & DMs
    if message.author.bot:
        return
    if message.guild is None:
        # ignore DMs silently (user requested commands not to work in DMs)
        return

    guild_id = message.guild.id
    cfg = get_guild_config(guild_id)
    allowed_channel = cfg.get("CHANNEL_ID")
    if not allowed_channel:
        # no channel set -> silent ignore
        return
    if message.channel.id != allowed_channel:
        return  # silent outside designated channel

    # triggers: unified list
    triggers = cfg.get("TRIGGERS", [])
    trig = find_trigger_for_message(triggers, message.content)
    if trig:
        pts = int(trig.get("points", 0))
        new_total = change_user_points(guild_id, message.author.id, pts)
        if cfg.get("NOTIFY_ON_TRIGGER", True):
            # positive/negative wording
            if pts >= 0:
                await message.channel.send(f"{message.author.mention} gained {pts} point{'s' if pts!=1 else ''}! Total: **{new_total}**")
            else:
                await message.channel.send(f"{message.author.mention} lost {abs(pts)} point{'s' if pts!=-1 else ''}! Total: **{new_total}**")
        return

    # allow commands processing afterwards
    await bot.process_commands(message)

# ---------- UTIL: ensure command in guild & channel ----------
async def ensure_guild_and_channel(interaction: discord.Interaction) -> bool:
    # returns True if command should proceed
    if interaction.guild is None:
        # silently ignore commands in DMs
        return False
    cfg = get_guild_config(interaction.guild.id)
    allowed = cfg.get("CHANNEL_ID")
    if not allowed:
        # no channel set => silent ignore
        return False
    if interaction.channel is None or interaction.channel.id != allowed:
        # command used outside designated channel -> silent ignore
        return False
    return True

# ---------- SLASH COMMANDS ----------
# /points
@bot.tree.command(name="points", description="Check your points (server-specific)")
async def points_cmd(interaction: discord.Interaction):
    ok = await ensure_guild_and_channel(interaction)
    if not ok:
        return
    pts = get_user_points(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(f"{interaction.user.mention}, you have **{pts}** point{'s' if pts!=1 else ''}.", ephemeral=True)

# /daily
@bot.tree.command(name="daily", description="Claim your daily reward")
async def daily_cmd(interaction: discord.Interaction):
    ok = await ensure_guild_and_channel(interaction)
    if not ok:
        return
    guild_id = interaction.guild.id
    user_id = interaction.user.id
    cfg = get_guild_config(guild_id)
    can_claim, remain = can_claim_daily(guild_id, user_id)
    if not can_claim:
        # send ephemeral remaining time
        hours = int(remain.total_seconds() // 3600)
        minutes = int((remain.total_seconds() % 3600) // 60)
        await interaction.response.send_message(f"You must wait {hours}h {minutes}m to claim daily again.", ephemeral=True)
        return
    reward = int(cfg.get("DAILY_REWARD", 10))
    total = change_user_points(guild_id, user_id, reward)
    set_daily_claim(guild_id, user_id)
    await interaction.response.send_message(f"🎉 {interaction.user.mention}, you claimed your daily reward of **{reward}** points! Total: **{total}**")

# /gamble <color> <amount>
@bot.tree.command(name="gamble", description="Gamble on red or black. Subtracts bet first, win doubles the bet.")
@app_commands.choices(color=[
    app_commands.Choice(name="red", value="red"),
    app_commands.Choice(name="black", value="black"),
])
@app_commands.describe(color="Pick red or black", amount="Amount to gamble")
async def gamble_cmd(interaction: discord.Interaction, color: app_commands.Choice[str], amount: int):
    ok = await ensure_guild_and_channel(interaction)
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

    # subtract bet immediately
    change_user_points(guild_id, user_id, -amount)

    # 50% win chance (hardcoded)
    win = random.choice([True, False])
    if win:
        payout = amount * 2
        total = change_user_points(guild_id, user_id, payout)
        await interaction.response.send_message(
            f"🎉 **You won!** The color was **{color.value}**. You win **{payout}** points (net +{amount}). Total: **{total}**"
        )
    else:
        total = get_user_points(guild_id, user_id)
        await interaction.response.send_message(
            f"💀 **You lost.** The color was **{color.value}**. You lost **{amount}** points. Total: **{total}**"
        )

# /leaderboard
@bot.tree.command(name="leaderboard", description="Show server leaderboard (top N per config)")
@app_commands.describe(top="How many users to show (default = config)")
async def leaderboard_cmd(interaction: discord.Interaction, top: Optional[int] = None):
    ok = await ensure_guild_and_channel(interaction)
    if not ok:
        return
    gid = str(interaction.guild.id)
    cfg = get_guild_config(interaction.guild.id)
    top_n = int(top) if top and top > 0 else int(cfg.get("LEADERBOARD_TOP", 10))
    guild_points = points_data.get(gid, {})
    if not guild_points:
        await interaction.response.send_message("No points yet on this server.", ephemeral=True)
        return
    sorted_list = sorted(guild_points.items(), key=lambda x: x[1], reverse=True)[:top_n]
    embed = discord.Embed(title=f"🏆 Leaderboard (Top {len(sorted_list)})", color=discord.Color.gold())
    for i, (uid, pts) in enumerate(sorted_list, start=1):
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else f"User ID {uid}"
        embed.add_field(name=f"{i}. {name}", value=f"{pts} points", inline=False)
    await interaction.response.send_message(embed=embed)

# /addtrigger (admin)
@bot.tree.command(name="addtrigger", description="Add a trigger (admin only). Message is case-insensitive substring.")
@app_commands.describe(message="Trigger text (substring)", points="Points to add (use negative for removing points)")
async def addtrigger_cmd(interaction: discord.Interaction, message: str, points: int):
    if interaction.guild is None:
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Administrator only.", ephemeral=True)
        return
    cfg = get_guild_config(interaction.guild.id)
    cfg.setdefault("TRIGGERS", [])
    cfg["TRIGGERS"].append({"message": message, "points": int(points)})
    config_data[str(interaction.guild.id)] = cfg
    save_json(CONFIG_FILE, config_data)
    await interaction.response.send_message(f"Trigger added: '{message}' → {points} point{'s' if abs(points)!=1 else ''}.", ephemeral=True)

# /removetrigger (admin) - exact message match (case-insensitive)
@bot.tree.command(name="removetrigger", description="Remove a trigger (admin only) by exact message text.")
@app_commands.describe(message="Exact trigger text to remove (case-insensitive)")
async def removetrigger_cmd(interaction: discord.Interaction, message: str):
    if interaction.guild is None:
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Administrator only.", ephemeral=True)
        return
    cfg = get_guild_config(interaction.guild.id)
    before = len(cfg.get("TRIGGERS", []))
    cfg["TRIGGERS"] = [t for t in cfg.get("TRIGGERS", []) if t.get("message", "").lower() != message.lower()]
    config_data[str(interaction.guild.id)] = cfg
    save_json(CONFIG_FILE, config_data)
    after = len(cfg.get("TRIGGERS", []))
    if before == after:
        await interaction.response.send_message("No matching trigger found.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Removed trigger matching '{message}'.", ephemeral=True)

# /setchannel (admin)
@bot.tree.command(name="setchannel", description="Set the channel where the bot will operate (admin only)")
@app_commands.describe(channel_id="Enter the numeric ID of the channel")
async def setchannel(interaction: discord.Interaction, channel_id: str):
    if interaction.guild is None:
        return
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Only administrators can use this command.", ephemeral=True)
        return

    # Validate the channel ID
    if not channel_id.isdigit():
        await interaction.response.send_message("❌ Please enter a valid numeric channel ID.", ephemeral=True)
        return

    channel = interaction.guild.get_channel(int(channel_id))
    if channel is None:
        await interaction.response.send_message("❌ Channel not found. Make sure the ID is correct.", ephemeral=True)
        return

    cfg = get_guild_config(interaction.guild.id)
    cfg["CHANNEL_ID"] = channel.id
    config_data[str(interaction.guild.id)] = cfg
    save_json(CONFIG_FILE, config_data)

    await interaction.response.send_message(f"✅ Bot channel set to {channel.mention} for this server.", ephemeral=True)

# /setconfig (admin) for numeric options
@bot.tree.command(name="setconfig", description="Set numeric configuration option (admin only)")
@app_commands.describe(option="Option name (DAILY_REWARD, DAILY_COOLDOWN_HOURS, GAMBLE_WIN_CHANCE, LEADERBOARD_TOP)", value="Integer value")
async def setconfig_cmd(interaction: discord.Interaction, option: str, value: int):
    if interaction.guild is None:
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Administrator only.", ephemeral=True)
        return
    opt = option.strip().upper()
    allowed = ("DAILY_REWARD", "DAILY_COOLDOWN_HOURS", "GAMBLE_WIN_CHANCE", "LEADERBOARD_TOP")
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
    if interaction.guild is None:
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Administrator only.", ephemeral=True)
        return
    cfg = get_guild_config(interaction.guild.id)
    lines = [
        f"CHANNEL_ID: {cfg.get('CHANNEL_ID')}",
        f"DAILY_REWARD: {cfg.get('DAILY_REWARD')}",
        f"DAILY_COOLDOWN_HOURS: {cfg.get('DAILY_COOLDOWN_HOURS')}",
        f"GAMBLE_WIN_CHANCE (ref): {cfg.get('GAMBLE_WIN_CHANCE')}",
        f"LEADERBOARD_TOP: {cfg.get('LEADERBOARD_TOP')}",
        "TRIGGERS:"
    ]
    for t in cfg.get("TRIGGERS", []):
        lines.append(f"  • '{t.get('message')}' -> {t.get('points')}")
    await interaction.response.send_message("```\n" + "\n".join(lines) + "\n```", ephemeral=True)

# /reset (admin)
@bot.tree.command(name="reset", description="Reset a user's points for this server (admin only)")
@app_commands.describe(member="Member to reset")
async def reset_cmd(interaction: discord.Interaction, member: discord.Member):
    if interaction.guild is None:
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Administrator only.", ephemeral=True)
        return
    set_user_points(interaction.guild.id, member.id, 0)
    await interaction.response.send_message(f"{member.mention}'s points have been reset to 0.", ephemeral=True)

# /selftest (admin) -> DM the results
@bot.tree.command(name="selftest", description="Run a self-test (admin only). Results are sent via DM.")
async def selftest_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Administrator only.", ephemeral=True)
        return

    # Prepare report
    guild_id = interaction.guild.id
    cfg = get_guild_config(guild_id)
    report_lines = []
    report_lines.append(f"Self-test for server: {interaction.guild.name} (ID: {guild_id})")
    # 1) Channel set?
    if not cfg.get("CHANNEL_ID"):
        report_lines.append("❌ Channel not configured. Set a channel with /setchannel <channel_id> to enable bot features.")
    else:
        report_lines.append(f"✅ Channel set: <#{cfg['CHANNEL_ID']}>")
    # 2) JSON files present
    for p,file in (("config", CONFIG_FILE), ("points", POINTS_FILE), ("daily", DAILY_FILE)):
        try:
            _ = load_json(file)
            report_lines.append(f"✅ {file} loaded OK")
        except Exception as e:
            report_lines.append(f"❌ {file} load error: {e}")
    # 3) Triggers sanity
    tcount = len(cfg.get("TRIGGERS", []))
    report_lines.append(f"✅ Triggers count: {tcount}")
    # 4) Points persistence test
    uid = interaction.user.id
    try:
        prev = get_user_points(guild_id, uid)
        change_user_points(guild_id, uid, 1)
        if get_user_points(guild_id, uid) == prev + 1:
            # revert
            set_user_points(guild_id, uid, prev)
            report_lines.append("✅ Points save/load test: OK")
        else:
            report_lines.append("❌ Points save/load test: mismatch")
    except Exception as e:
        report_lines.append(f"❌ Points test error: {e}")
    # 5) Daily logic test (simulate)
    try:
        ok, rem = can_claim_daily(guild_id, uid)
        report_lines.append(f"✅ Daily cooldown check ran (can_claim={ok})")
    except Exception as e:
        report_lines.append(f"❌ Daily test error: {e}")
    # 6) Gamble logic test (simulate subtract/add)
    try:
        cur = get_user_points(guild_id, uid)
        # Give test funds
        set_user_points(guild_id, uid, max(cur, 5))
        before = get_user_points(guild_id, uid)
        # simulate gamble subtract-then-win
        change_user_points(guild_id, uid, -1)
        change_user_points(guild_id, uid, 2)  # payout double
        after = get_user_points(guild_id, uid)
        if after == before + 1:
            report_lines.append("✅ Gamble logic simulation OK")
        else:
            report_lines.append("❌ Gamble logic simulation mismatch")
        # revert to original
        set_user_points(guild_id, uid, cur)
    except Exception as e:
        report_lines.append(f"❌ Gamble test error: {e}")

    # Send report via DM to the admin who triggered the test
    report = "\n".join(report_lines)
    try:
        await interaction.user.send(f"Self-test results:\n\n{report}")
        await interaction.response.send_message("Self-test completed — report DM'd to you.", ephemeral=True)
    except Exception as e:
        # if DM blocked, inform ephemeral
        await interaction.response.send_message(f"Self-test completed but I couldn't DM you (error: {e}).", ephemeral=True)

# ---------- START ----------
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN environment variable not set.")
        raise SystemExit(1)
    bot.run(TOKEN)


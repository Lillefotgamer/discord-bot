import discord
from discord.ext import commands, tasks
import json, os, random, asyncio, datetime

TOKEN = os.getenv("DISCORD_TOKEN")
CONFIG_FILE = "config.json"
POINTS_FILE = "points.json"

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

# Load per-server configuration
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    config = {}

# Load points
if os.path.exists(POINTS_FILE):
    with open(POINTS_FILE, "r") as f:
        points = json.load(f)
else:
    points = {}

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def save_points():
    with open(POINTS_FILE, "w") as f:
        json.dump(points, f, indent=4)

def get_server_config(guild_id):
    guild_id = str(guild_id)
    if guild_id not in config:
        config[guild_id] = {
            "channel_id": None,
            "daily_reward": 10,
            "daily_cooldown_hours": 24,
            "gamble_win_chance": 0.5,
            "gamble_multiplier": 2,
            "add_triggers": [],
            "remove_triggers": [],
            "dm_message": "meow (i only work in specific channels.)",
            "gamble_messages": {
                "win": "🎉 You won! You gain {points} points! Total: **{total}**",
                "lose": "😢 You lost! You lose {points} points! Total: **{total}**"
            }
        }
    return config[guild_id]

def ensure_user_points(guild_id, user_id):
    guild_id = str(guild_id)
    user_id = str(user_id)
    if guild_id not in points:
        points[guild_id] = {}
    if user_id not in points[guild_id]:
        points[guild_id][user_id] = 0
    return points[guild_id][user_id]

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    await bot.tree.sync()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # DM handling
    if isinstance(message.channel, discord.DMChannel):
        await message.channel.send("I only work inside servers.")
        return

    guild_id = str(message.guild.id)
    server_config = get_server_config(message.guild.id)
    if server_config["channel_id"] and message.channel.id != server_config["channel_id"]:
        return  # silent outside set channel

    content = message.content.lower()
    user_id = str(message.author.id)

    # Check add triggers
    for trig in server_config["add_triggers"]:
        if trig.lower() in content:
            points[guild_id][user_id] = ensure_user_points(message.guild.id, user_id) + 1
            save_points()
            await message.channel.send(f"{message.author.mention}, you gained 1 point! Total: **{points[guild_id][user_id]}**")
            break

    # Check remove triggers
    for trig in server_config["remove_triggers"]:
        if trig.lower() in content:
            points[guild_id][user_id] = ensure_user_points(message.guild.id, user_id) - 1
            save_points()
            await message.channel.send(f"{message.author.mention}, you lost 1 point! Total: **{points[guild_id][user_id]}**")
            break

    await bot.process_commands(message)

# ----- Slash Commands -----
@bot.tree.command(description="Claim your daily reward")
async def daily(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)
    server_config = get_server_config(interaction.guild.id)

    if server_config["channel_id"] and interaction.channel.id != server_config["channel_id"]:
        await interaction.response.send_message(server_config["dm_message"], ephemeral=True)
        return

    user_points = ensure_user_points(interaction.guild.id, user_id)
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    cooldown_key = f"{user_id}_{today}"

    if "daily_claimed" not in server_config:
        server_config["daily_claimed"] = {}

    claimed = server_config["daily_claimed"].get(cooldown_key, 0)
    hours_passed = claimed

    if claimed:
        remaining = server_config["daily_cooldown_hours"] - hours_passed
        await interaction.response.send_message(f"You already claimed daily. Wait {remaining} hours.", ephemeral=True)
        return

    user_points += server_config["daily_reward"]
    ensure_user_points(interaction.guild.id, user_id)
    points[guild_id][user_id] = user_points
    save_points()
    server_config["daily_claimed"][cooldown_key] = server_config["daily_cooldown_hours"]
    save_config()
    await interaction.response.send_message(f"{interaction.user.mention}, you claimed your daily reward of {server_config['daily_reward']} points! Total: **{user_points}**")

@bot.tree.command(description="Gamble your points")
async def gamble(interaction: discord.Interaction, amount: int):
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)
    server_config = get_server_config(interaction.guild.id)

    if server_config["channel_id"] and interaction.channel.id != server_config["channel_id"]:
        await interaction.response.send_message(server_config["dm_message"], ephemeral=True)
        return

    user_points = ensure_user_points(interaction.guild.id, user_id)
    if amount > user_points:
        await interaction.response.send_message("You don't have enough points.", ephemeral=True)
        return

    win = random.random() < server_config["gamble_win_chance"]
    if win:
        gained = amount * server_config["gamble_multiplier"]
        points[guild_id][user_id] += gained
        await interaction.response.send_message(server_config["gamble_messages"]["win"].format(points=gained, total=points[guild_id][user_id]))
    else:
        points[guild_id][user_id] -= amount
        await interaction.response.send_message(server_config["gamble_messages"]["lose"].format(points=amount, total=points[guild_id][user_id]))
    save_points()

# ----- Admin Commands -----
def admin_check(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

@bot.tree.command(description="Reset a user's points")
async def reset(interaction: discord.Interaction, member: discord.Member):
    if not admin_check(interaction):
        await interaction.response.send_message("You must be an admin.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(member.id)
    points[guild_id][user_id] = 0
    save_points()
    await interaction.response.send_message(f"{member.mention}'s points have been reset.")

@bot.tree.command(description="Set configuration for the server")
async def setconfig(interaction: discord.Interaction, option: str, value: str):
    if not admin_check(interaction):
        await interaction.response.send_message("You must be an admin.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    server_config = get_server_config(interaction.guild.id)
    if option not in server_config:
        await interaction.response.send_message("Invalid option.", ephemeral=True)
        return
    if option in ["channel_id", "daily_reward", "daily_cooldown_hours"]:
        value = int(value)
    server_config[option] = value
    save_config()
    await interaction.response.send_message(f"Config {option} updated to {value}.")

@bot.tree.command(description="Add a message trigger for adding points")
async def addtrigger(interaction: discord.Interaction, message: str):
    if not admin_check(interaction):
        await interaction.response.send_message("You must be an admin.", ephemeral=True)
        return
    server_config = get_server_config(interaction.guild.id)
    server_config["add_triggers"].append(message)
    save_config()
    await interaction.response.send_message(f"Added positive trigger: `{message}`")

@bot.tree.command(description="Remove a message trigger")
async def removetrigger(interaction: discord.Interaction, message: str):
    if not admin_check(interaction):
        await interaction.response.send_message("You must be an admin.", ephemeral=True)
        return
    server_config = get_server_config(interaction.guild.id)
    if message in server_config["add_triggers"]:
        server_config["add_triggers"].remove(message)
        save_config()
        await interaction.response.send_message(f"Removed trigger: `{message}`")
    else:
        await interaction.response.send_message("Trigger not found.")

@bot.tree.command(description="Show current server configurations")
async def currentconfigurations(interaction: discord.Interaction):
    if not admin_check(interaction):
        await interaction.response.send_message("You must be an admin.", ephemeral=True)
        return
    server_config = get_server_config(interaction.guild.id)
    embed = discord.Embed(title="Server Configurations", color=discord.Color.blue())
    for k,v in server_config.items():
        embed.add_field(name=k, value=str(v), inline=False)
    await interaction.response.send_message(embed=embed)

bot.run(TOKEN)

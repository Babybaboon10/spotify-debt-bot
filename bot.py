import discord
from discord import app_commands
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import calendar
import os
import json

# -------- LOAD GOOGLE CREDENTIALS --------

google_creds = json.loads(os.getenv("GOOGLE_CREDENTIALS"))

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    google_creds,
    scopes=scope
)

gs_client = gspread.authorize(creds)
sheet = gs_client.open("Spotify").sheet1


# -------- CACHE + LOOKUPS --------

sheet_cache = []
month_rows = {}
user_columns = {}


def refresh_sheet():
    global sheet_cache, month_rows, user_columns

    sheet_cache = sheet.get_all_values()

    month_rows = {}
    user_columns = {}

    for i, row in enumerate(sheet_cache):
        if row and row[0]:
            month_rows[row[0]] = i

    header = sheet_cache[2]

    for i, cell in enumerate(header):
        name = cell.strip()
        if name:
            user_columns[name] = i + 1


# -------- DISCORD SETUP --------

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

GUILD_ID = 1481367910965579809
guild = discord.Object(id=GUILD_ID)


# -------- USER MAP --------

user_names = {
    641448694691921930: "Dylan",
    521798405295439873: "Mason",
    521367028167344163: "Eamon",
    389038935642341377: "Dominic",
    614181100365021207: "Gavin"
}


# -------- HELPERS --------

def get_current_month():
    now = datetime.now()
    month = calendar.month_abbr[now.month]
    return f"{month} {now.year}"


def find_future_debt(start_row, column):

    for r in range(start_row + 1, len(sheet_cache)):

        value = sheet_cache[r][column]

        try:
            debt = float(value.replace("$", ""))
        except:
            continue

        if debt > 0:
            return sheet_cache[r][0]

    return None


# -------- COMMANDS --------

@tree.command(name="debt", description="Check Spotify debt", guild=guild)
@app_commands.describe(user="Optional user to check")
async def debt(interaction: discord.Interaction, user: discord.Member | None = None):

    if user is None:
        user_id = interaction.user.id
    else:
        user_id = user.id

    if user_id not in user_names:
        await interaction.response.send_message(
            "That user isn't registered in the spreadsheet."
        )
        return

    name = user_names[user_id]

    row = month_rows.get(get_current_month())
    column = user_columns.get(name)

    value = sheet_cache[row][column]

    try:
        debt_value = float(value.replace("$", ""))
    except:
        debt_value = 0

    embed = discord.Embed(
        title="Spotify Debt",
        color=discord.Color.green()
    )

    if debt_value > 0:

        embed.add_field(
            name=name,
            value=f"Debt for **{get_current_month()}**: `${debt_value:.2f}`",
            inline=False
        )

    else:

        future = find_future_debt(row, column)

        if future:
            embed.add_field(
                name=name,
                value=f"You will not be in debt until **{future}**",
                inline=False
            )
        else:
            embed.add_field(
                name=name,
                value="No future debt found in spreadsheet.",
                inline=False
            )

    await interaction.response.send_message(embed=embed)


@tree.command(name="status", description="Show everyone's current standing", guild=guild)
async def status(interaction: discord.Interaction):

    row = month_rows.get(get_current_month())

    debt_list = []

    for name in user_columns:

        column = user_columns[name]
        value = sheet_cache[row][column]

        try:
            debt = float(value.replace("$", ""))
        except:
            debt = 0

        debt_list.append((name, debt))

    debt_list.sort(key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title=f"Spotify Debt Status ({get_current_month()})",
        color=discord.Color.blue()
    )

    for name, debt in debt_list:

        if debt > 0:
            embed.add_field(name=name, value=f"${debt:.2f}", inline=False)
        else:
            embed.add_field(name=name, value="credit", inline=False)

    await interaction.response.send_message(embed=embed)


@tree.command(name="whoisindebt", description="Show people currently in debt", guild=guild)
async def whoisindebt(interaction: discord.Interaction):

    row = month_rows.get(get_current_month())

    embed = discord.Embed(
        title=f"People Currently in Debt ({get_current_month()})",
        color=discord.Color.red()
    )

    anyone = False

    for name in user_columns:

        column = user_columns[name]
        value = sheet_cache[row][column]

        try:
            debt = float(value.replace("$", ""))
        except:
            debt = 0

        if debt > 0:
            embed.add_field(name=name, value=f"${debt:.2f}", inline=False)
            anyone = True

    if not anyone:
        embed.description = "Nobody currently owes anything 🎉"

    await interaction.response.send_message(embed=embed)


@tree.command(name="nextdebt", description="Show when people with credit will owe again", guild=guild)
async def nextdebt(interaction: discord.Interaction):

    row = month_rows.get(get_current_month())

    embed = discord.Embed(
        title="Next Debt Forecast",
        color=discord.Color.orange()
    )

    for name in user_columns:

        column = user_columns[name]
        value = sheet_cache[row][column]

        try:
            debt = float(value.replace("$", ""))
        except:
            debt = 0

        if debt <= 0:

            future = find_future_debt(row, column)

            if future:
                embed.add_field(name=name, value=future, inline=False)
            else:
                embed.add_field(name=name, value="No future debt found", inline=False)

    await interaction.response.send_message(embed=embed)


@tree.command(name="refresh", description="Reload spreadsheet cache", guild=guild)
async def refresh(interaction: discord.Interaction):

    refresh_sheet()

    await interaction.response.send_message(
        "Spreadsheet cache refreshed.", ephemeral=True
    )


# -------- DEV COMMANDS --------

@tree.command(name="sync", description="Force command resync", guild=guild)
async def sync(interaction: discord.Interaction):

    if interaction.user.id != 614181100365021207:
        await interaction.response.send_message(
            "You can't use this command.", ephemeral=True
        )
        return

    # wipe global commands from Discord API
    tree.clear_commands(guild=None)
    await tree.sync()

    # rebuild guild commands
    await tree.sync(guild=guild)

    await interaction.response.send_message(
        "Global commands cleared and guild commands rebuilt.", ephemeral=True
    )


@tree.command(name="debugsheet", description="Debug spreadsheet cache", guild=guild)
async def debugsheet(interaction: discord.Interaction):

    if interaction.user.id != 614181100365021207:
        await interaction.response.send_message(
            "You can't use this command.", ephemeral=True
        )
        return

    msg = f"""
Rows cached: {len(sheet_cache)}

Months detected:
{list(month_rows.keys())[:5]}

User columns:
{user_columns}
"""

    await interaction.response.send_message(msg, ephemeral=True)


# -------- BOT STARTUP --------

@client.event
async def on_ready():

    # send empty array to global command API
    tree.clear_commands(guild=None)
    await tree.sync()

    # rebuild guild commands
    await tree.sync(guild=guild)

    refresh_sheet()

    print(f"Logged in as {client.user}")


client.run(os.getenv("DISCORD_TOKEN"))


import discord
from discord import app_commands
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import calendar
import os
import json

# -------- LOAD GOOGLE CREDENTIALS FROM ENV --------

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


# -------- CACHE --------

sheet_cache = []


def refresh_sheet():
    global sheet_cache
    sheet_cache = sheet.get_all_values()


# -------- DISCORD SETUP --------

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# Discord ID → spreadsheet name
user_names = {
    641448694691921930: "Dylan",
    521798405295439873: "Mason",
    521367028167344163: "Eamon",
    389038935642341377: "Dominic",
    614181100365021207: "Gavin"
}


# -------- HELPERS --------

def find_debt_column(name):

    header = sheet_cache[2]  # row 3 in spreadsheet

    for i, cell in enumerate(header):

        if cell.strip().lower() == name.lower():
            return i + 1

    return None


def find_current_month_row():

    now = datetime.now()
    month = calendar.month_abbr[now.month]
    current_month = f"{month} {now.year}"

    for i, row in enumerate(sheet_cache):

        if row[0] == current_month:
            return i

    return None


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

@tree.command(name="debt", description="Check Spotify debt")
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

    row = find_current_month_row()

    if row is None:

        await interaction.response.send_message(
            "Current month not found in spreadsheet."
        )
        return

    column = find_debt_column(name)

    if column is None:

        await interaction.response.send_message(
            f"Could not find column for {name}."
        )
        return

    value = sheet_cache[row][column]

    try:
        debt = float(value.replace("$", ""))
    except:
        debt = 0

    if debt > 0:

        now = datetime.now()
        month = calendar.month_abbr[now.month]
        current_month = f"{month} {now.year}"

        await interaction.response.send_message(
            f"{name}, your **{current_month}** debt is **${debt:.2f}**"
        )

    else:

        future_month = find_future_debt(row, column)

        if future_month:

            await interaction.response.send_message(
                f"{name}, you will not be in debt until **{future_month}**."
            )

        else:

            await interaction.response.send_message(
                f"{name} will not be in debt in any listed future month."
            )


@tree.command(name="refresh", description="Reload spreadsheet cache")
async def refresh(interaction: discord.Interaction):

    refresh_sheet()

    await interaction.response.send_message("Spreadsheet cache refreshed.")


# -------- BOT STARTUP --------

@client.event
async def on_ready():

    await tree.sync()

    refresh_sheet()

    print(f"Logged in as {client.user}")


client.run(os.getenv("DISCORD_TOKEN"))
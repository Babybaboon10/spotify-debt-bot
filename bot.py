import discord
from discord import app_commands
from discord.ext import tasks
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import calendar
import os
import json
import time
from zoneinfo import ZoneInfo

# -------- ENV VARIABLES --------

SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
REMINDER_CHANNEL_ID = 1481466539591864320

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

def get_now_est():
    return datetime.now(ZoneInfo("America/New_York"))

def get_current_month():
    now = get_now_est()
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


# -------- PAYMENT COOLDOWN --------

last_payment_time = {}


# -------- COMMANDS --------

@tree.command(name="debt", description="Check Spotify debt", guild=guild)
@app_commands.describe(user="Optional user to check")
async def debt(interaction: discord.Interaction, user: discord.Member | None = None):

    user_id = interaction.user.id if user is None else user.id

    if user_id not in user_names:
        await interaction.response.send_message("User not registered.")
        return

    name = user_names[user_id]

    row = month_rows.get(get_current_month())
    column = user_columns.get(name)

    value = sheet_cache[row][column]

    try:
        debt_value = float(value.replace("$", ""))
    except:
        debt_value = 0

    embed = discord.Embed(title="Spotify Debt", color=discord.Color.green())

    if debt_value > 0:
        embed.add_field(name=name, value=f"${debt_value:.2f}", inline=False)
    else:
        future = find_future_debt(row, column)
        embed.add_field(
            name=name,
            value=f"No debt until {future}" if future else "No future debt",
            inline=False
        )

    await interaction.response.send_message(embed=embed)


@tree.command(name="status", description="Show everyone's current debt", guild=guild)
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
        embed.add_field(
            name=name,
            value=f"${debt:.2f}" if debt > 0 else "credit",
            inline=False
        )

    await interaction.response.send_message(embed=embed)


@tree.command(name="whoisindebt", description="Show people currently in debt", guild=guild)
async def whoisindebt(interaction: discord.Interaction):

    row = month_rows.get(get_current_month())

    embed = discord.Embed(title="People in Debt", color=discord.Color.red())

    for name in user_columns:
        column = user_columns[name]
        value = sheet_cache[row][column]

        try:
            debt = float(value.replace("$", ""))
        except:
            debt = 0

        if debt > 0:
            embed.add_field(name=name, value=f"${debt:.2f}", inline=False)

    await interaction.response.send_message(embed=embed)


@tree.command(name="nextdebt", description="Future debt forecast", guild=guild)
async def nextdebt(interaction: discord.Interaction):

    row = month_rows.get(get_current_month())

    embed = discord.Embed(title="Next Debt Forecast", color=discord.Color.orange())

    for name in user_columns:
        column = user_columns[name]
        value = sheet_cache[row][column]

        try:
            debt = float(value.replace("$", ""))
        except:
            debt = 0

        if debt <= 0:
            future = find_future_debt(row, column)
            embed.add_field(name=name, value=future or "No future debt", inline=False)

    await interaction.response.send_message(embed=embed)


@tree.command(name="paid", description="Record payment", guild=guild)
async def paid(interaction: discord.Interaction, user: discord.Member, amount: float):

    now = time.time()

    if interaction.user.id in last_payment_time:
        if now - last_payment_time[interaction.user.id] < 5:
            await interaction.response.send_message(
                "Too fast — possible duplicate.",
                ephemeral=True
            )
            return

    last_payment_time[interaction.user.id] = now

    user_id = user.id

    if user_id not in user_names:
        await interaction.response.send_message("User not registered.", ephemeral=True)
        return

    name = user_names[user_id]

    row = month_rows.get(get_current_month())
    debt_col = user_columns.get(name)
    paid_col = debt_col - 1

    current_value = sheet_cache[row][paid_col]

    try:
        current = float(current_value.replace("$", "").strip())
    except:
        current = 0.0

    new_total = current + amount

    sheet.update_cell(row + 1, paid_col + 1, new_total)

    refresh_sheet()

    await interaction.response.send_message(
        f"{name} paid ${amount:.2f} (total: ${new_total:.2f})"
    )


@tree.command(name="link", description="Get spreadsheet link", guild=guild)
async def link(interaction: discord.Interaction):
    await interaction.response.send_message(SPREADSHEET_URL, ephemeral=True)


@tree.command(name="refresh", description="Reload cache", guild=guild)
async def refresh(interaction: discord.Interaction):
    refresh_sheet()
    await interaction.response.send_message("Cache refreshed.", ephemeral=True)


# -------- REMINDER TASK --------

@tasks.loop(minutes=30)
async def monthly_reminder():

    now = get_now_est()

    if now.day == 3 and now.hour == 10:

        row = month_rows.get(get_current_month())
        if row is None:
            return

        people_in_debt = []

        for user_id, name in user_names.items():

            debt_col = user_columns.get(name)
            paid_col = debt_col - 1

            # Fill empty paid cells with 0
            paid_value = sheet_cache[row][paid_col]
            if not paid_value or paid_value.strip() == "":
                sheet.update_cell(row + 1, paid_col + 1, 0)

            # Check debt
            value = sheet_cache[row][debt_col]

            try:
                debt = float(value.replace("$", ""))
            except:
                debt = 0

            if debt > 0:
                people_in_debt.append(user_id)

        refresh_sheet()

        if not people_in_debt:
            return

        channel = client.get_channel(REMINDER_CHANNEL_ID)

        if channel:
            mentions = " ".join(f"<@{uid}>" for uid in people_in_debt)
            await channel.send(
                f"{mentions}\nReminder: You currently owe money for Spotify — please settle up!"
            )


# -------- DEV COMMAND --------

@tree.command(name="sync", description="Resync commands", guild=guild)
async def sync(interaction: discord.Interaction):

    if interaction.user.id != 614181100365021207:
        await interaction.response.send_message("Nope.", ephemeral=True)
        return

    tree.clear_commands(guild=None)
    await tree.sync()
    await tree.sync(guild=guild)

    await interaction.response.send_message("Synced.", ephemeral=True)


# -------- STARTUP --------

@client.event
async def on_ready():

    tree.clear_commands(guild=None)
    await tree.sync()
    await tree.sync(guild=guild)

    refresh_sheet()

    monthly_reminder.start()

    print(f"Logged in as {client.user}")


client.run(os.getenv("DISCORD_TOKEN"))

import discord
import discord.ext
from discord.ext import tasks, commands
from discord import app_commands, Interaction
from queue import Queue
from time import sleep
from threading import Thread
from dotenv import load_dotenv, find_dotenv
import os


load_dotenv(find_dotenv())
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID")
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix='$', intents=intents)
bot2 = discord.Client(command_prefix="$", intents=intents)
tree = app_commands.CommandTree(bot2)


@tree.command(name="set_ranges", description="set the price range limit of btc for trading to be active", )
async def set_btc_ranges(interaction: Interaction, upper: float, lower: float):
    print("hi")
    await interaction.response.send_message(f"{upper, lower}")


@bot.hybrid_command(name="test")
async def test(ctx):
    await ctx.send("this is a hybrid command")


@tree.command(name="name", description="description")
async def slash_command(interaction: discord.Interaction):
    await interaction.response.send_message("hu")


@bot.event
async def on_ready():
    await tree.sync()
    print("Ready!")


client.run(DISCORD_TOKEN)

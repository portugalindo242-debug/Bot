import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot online como {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("Pong! 🏓")

bot.run(os.environ["MTU1MzUzNjk5MTA5MjY3ODY4Nw.Gr8fp1.IuA6NI3BkfgE25dtHTOhKLZe9nvFkOtTzvj_hg"])

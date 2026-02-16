import discord
from discord.ext import commands
import asyncio
import traceback
import re

# Import configuration
from config.config import config

# Import modules
from music import setup_music_commands
from osrs.wiki import setup_osrs_commands
from osrs.wiseoldman import setup_competition_commands

# Define the intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

def case_insensitive_prefix(bot, message):
    # Just return a single lowercase prefix
    prefix = "!"
    return commands.when_mentioned_or(prefix)(bot, message)

class CaseInsensitiveBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        self.other_bot_commands = kwargs.pop('other_bot_commands', set())
        self.allowed_channel_keywords = {'music', 'command', 'bot', 'yomi'}

        # Enable case-insensitive commands
        super().__init__(*args, **kwargs, case_insensitive=True)

    async def get_context(self, message, *, cls=commands.Context):
        ctx = await super().get_context(message, cls=cls)

        channel_name = message.channel.name.lower()
        invoked = (ctx.invoked_with or "").lower()
        
        if invoked not in ("sotw", "botw", "askyomi", "ask", "yomi", "about", "player", "lookup", "roll") and not any(keyword in channel_name for keyword in self.allowed_channel_keywords):
            return None
            
        if (invoked == "askyomi" or invoked == "ask" or invoked == "yomi") and "yomi" not in channel_name:
            return None
        
        if ctx.prefix is None:
            return ctx
        
        if ctx.invoked_with and ctx.invoked_with.lower() in self.other_bot_commands:
            ctx.command = None
        
        return ctx

    async def process_commands(self, message):
        if message.author.bot:
            return

        ctx = await self.get_context(message)
        if ctx is None:
            return

        if ctx.command is None:
            if ctx.invoked_with and ctx.invoked_with.lower() not in self.other_bot_commands:
                await self.on_command_error(ctx, commands.CommandNotFound(f'Command "{ctx.invoked_with}" is not found'))
            return

        await self.invoke(ctx)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send(f'Sorry, I did not recognize that command. Please check your input and try again.')
        else:
            print(f"An error occurred: {error}")
            await ctx.send("An error occurred while processing the command.")

# Commands that other bots in the server might use
other_bot_commands = set()

# Create the bot instance
bot = CaseInsensitiveBot(command_prefix=case_insensitive_prefix, intents=intents, other_bot_commands=other_bot_commands)

# Set up event handlers
@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user}')

@bot.event
async def on_disconnect():
    print("Bot disconnected! Attempting to reconnect...")

@bot.event
async def on_resumed():
    print("Bot reconnected!")

@bot.event
async def on_error(event_method, *args, **kwargs):
    if args and isinstance(args[0], discord.errors.ConnectionClosed):
        print(f"ConnectionClosed error occurred in {event_method}: {args[0].code}")
    else:
        print(f"An error occurred in {event_method}:")
        traceback.print_exc()

# Basic bot information command
@bot.command(name='about', help='Provides information about the bot')
async def about(ctx):
    await ctx.send("YomiBot was created by CyanideByte for OSRS Clan Mesa.")

# Set up module commands
setup_music_commands(bot)
setup_osrs_commands(bot)
setup_competition_commands(bot)

if __name__ == "__main__":
    # Check for required environment variables
    if not config.gemini_api_key:
        print("Warning: GEMINI_API_KEY environment variable is not set. The !askyomi command will not work.")
    
    # Run the bot
    bot.run(config.bot_token)
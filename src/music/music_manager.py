import asyncio
import discord
import json
import os
import re
import time
from config.config import PROJECT_ROOT

QUEUE_DIR = os.path.join(PROJECT_ROOT, 'data', 'queues')

# Ensure queue directory exists
if not os.path.exists(QUEUE_DIR):
    os.makedirs(QUEUE_DIR)

def save_queue(server_id, queue_data):
    """Save the queue data for a server to a file"""
    queue_file = os.path.join(QUEUE_DIR, f'queue_{server_id}.json')
    with open(queue_file, 'w') as f:
        json.dump(queue_data, f, indent=4)

def load_queue(server_id):
    """Load the queue data for a server from a file"""
    queue_file = os.path.join(QUEUE_DIR, f'queue_{server_id}.json')
    if os.path.exists(queue_file):
        with open(queue_file, 'r') as f:
            return json.load(f)
    return []

def save_currently_playing(guild_id, current_song_data, next_song_data=None):
    """Save the currently playing song data to a file"""
    currently_playing = {
        "title": current_song_data.title,
        "channel": current_song_data.channel,
        "duration": current_song_data.duration,
        "url": current_song_data.original_url,
        "start_time": int(time.time())
    }

    next_song = None
    if next_song_data:
        next_song = {
            "title": next_song_data.title,
            "channel": next_song_data.channel,
            "duration": next_song_data.duration,
            "url": next_song_data.original_url
        }

    data = {
        "currently_playing": currently_playing,
        "next_song": next_song
    }

    file_path = os.path.join(QUEUE_DIR, f'currently_playing_{guild_id}.json')
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def normalize_youtube_music_url(url):
    """Normalize YouTube Music URLs to standard YouTube URLs"""
    if 'watch' in url:
        url = re.sub(r'(\?|&)list=.+', '', url)
    url = re.sub(r'(\?|&)start_radio=1', '', url)
    url = re.sub(r'(\?|&)si=.+', '', url)
    url = url.replace('music.youtube.com', 'www.youtube.com')
    return url

from .music_sources import YTDLSource

# Server state dictionary to track music playback state
servers = {}

async def get_server_state(ctx):
    """Get or initialize the server state for a guild"""
    server_id = ctx.guild.id
    if server_id not in servers:
        servers[server_id] = {
            'queue': [],
            'current_song': None,
            'next_song': None
        }
        queue = load_queue(server_id)
        if queue:
            servers[server_id]['queue'] = queue
    return servers[server_id]

async def play_next(ctx):
    """Play the next song in the queue"""
    from .music_sources import ffmpeg_options

    state = await get_server_state(ctx)
    if state['next_song']:
        state['current_song'] = state['next_song']
        state['next_song'] = None
        save_queue(ctx.guild.id, state['queue'])
    elif state['queue']:
        player_data = state['queue'].pop(0)

        # Check if this is a direct URL (e.g., .mp3 from cyanide.wtf)
        if player_data.get('is_direct_url'):
            # Create a direct audio source
            state['current_song'] = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(player_data['url'], **ffmpeg_options),
                volume=0.5
            )
            # Add metadata for display
            state['current_song'].data = player_data
            state['current_song'].title = player_data['title']
            state['current_song'].channel = player_data.get('channel', 'Unknown')
            state['current_song'].duration = player_data.get('duration', 0)
            state['current_song'].original_url = player_data['url']
            # Add cleanup method
            state['current_song'].cleanup = lambda: None
        else:
            try:
                state['current_song'] = await YTDLSource.from_url(player_data['url'], loop=asyncio.get_event_loop(), stream=True)
            except Exception as e:
                await ctx.send(f'Skipping song "{player_data["title"]}" due to error: {str(e)}')
                await play_next(ctx)
                return
    else:
        state['current_song'] = None
        await disconnect_after_timeout(ctx.voice_client, 300, ctx)
        return

    if ctx.voice_client and ctx.voice_client.is_connected():
        try:
            # Store the event loop reference
            loop = asyncio.get_event_loop()

            # Define a callback function that handles the event loop properly
            def after_callback(error):
                try:
                    # Try to get the current event loop
                    current_loop = asyncio.get_event_loop()
                except RuntimeError:
                    # If there's no event loop in this thread, use the stored one
                    asyncio.run_coroutine_threadsafe(on_song_end(ctx, error), loop)
                else:
                    # If we have an event loop in this thread, use it
                    asyncio.create_task(on_song_end(ctx, error))

            ctx.voice_client.play(state['current_song'], after=after_callback)
            print(f"Started playing: {state['current_song'].title}")

            # Save currently playing info
            if hasattr(state['current_song'], 'data'):
                save_currently_playing(ctx.guild.id, state['current_song'], state['next_song'])
        except discord.errors.ClientException:
            print("Already playing audio.")
            return
        title = state['current_song'].title
        duration = state['current_song'].duration if hasattr(state['current_song'], 'duration') else 0
        if duration > 0:
            await ctx.send(f'**Now playing:** {title} [{duration//60}:{duration%60:02d}]')
        else:
            await ctx.send(f'**Now playing:** {title}')
        await preload_next_song(ctx)
    else:
        print("Bot is not connected to a voice channel.")

async def preload_next_song(ctx):
    """Preload the next song in the queue to reduce delay between songs"""
    from .music_sources import ffmpeg_options

    print("Preloading the next song...")
    state = await get_server_state(ctx)

    if state['queue']:
        player_data = state['queue'].pop(0)
        print(f"Attempting to preload song: {player_data['title']}")

        # Check if this is a direct URL (e.g., .mp3 from cyanide.wtf)
        if player_data.get('is_direct_url'):
            # Create a direct audio source for preloading
            state['next_song'] = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(player_data['url'], **ffmpeg_options),
                volume=0.5
            )
            # Add metadata for display
            state['next_song'].data = player_data
            state['next_song'].title = player_data['title']
            state['next_song'].channel = player_data.get('channel', 'Unknown')
            state['next_song'].duration = player_data.get('duration', 0)
            state['next_song'].original_url = player_data['url']
            # Add cleanup method
            state['next_song'].cleanup = lambda: None
            print(f"Preloaded direct URL: {state['next_song'].title}")
        else:
            try:
                state['next_song'] = await YTDLSource.from_url(player_data['url'], loop=asyncio.get_event_loop(), stream=True)
                if state['next_song']:
                    print(f"Preloaded song: {state['next_song'].title}")
                else:
                    print("Failed to preload the song, no data returned.")
            except Exception as e:
                await ctx.send(f'Skipping track "{player_data["title"]}" due to error: {str(e)}')
                await preload_next_song(ctx)
                return

        if state['current_song']:
            # Only save if current_song has the right attributes
            if hasattr(state['current_song'], 'title'):
                save_currently_playing(ctx.guild.id, state['current_song'], state['next_song'])
    else:
        state['next_song'] = None
        print("No songs in queue to preload.")
        if state['current_song'] and hasattr(state['current_song'], 'title'):
            save_currently_playing(ctx.guild.id, state['current_song'])

async def on_song_end(ctx, error):
    """Handle song end event"""
    state = await get_server_state(ctx)
    if error:
        print(f"Player error: {error}")
        await ctx.send(f"Player error: {error}")
        if state['current_song']:
            state['current_song'].cleanup()
    else:
        print("Song ended successfully.")
    
    if ctx.voice_client and ctx.voice_client.channel:
        voice_channel = ctx.voice_client.channel
        if len(voice_channel.members) == 1 and voice_channel.members[0] == ctx.bot.user:
            await ctx.send("No more users in the voice channel. Leaving the voice channel.")
            await ctx.voice_client.disconnect()
            return

        if ctx.voice_client.is_connected():
            await play_next(ctx)
    else:
        print("Bot is not connected to a voice channel.")

async def disconnect_after_timeout(voice_client, timeout, ctx):
    """Disconnect from voice channel after a timeout period of inactivity"""
    await asyncio.sleep(timeout)
    if voice_client and not voice_client.is_playing() and voice_client.is_connected():
        await ctx.send("No more songs in the queue. Leaving the voice channel due to inactivity.")
        await voice_client.disconnect()

def clear_queue_and_current_song(ctx):
    """Clear the queue and current song"""
    state = servers.get(ctx.guild.id, None)
    if not state:
        return
    
    if state['current_song']:
        state['current_song'].cleanup()
        state['current_song'] = None
    
    if state['next_song']:
        state['next_song'].cleanup()
        state['next_song'] = None
    
    state['queue'] = []
    save_queue(ctx.guild.id, state['queue'])
    currently_playing_file = os.path.join(QUEUE_DIR, f'currently_playing_{ctx.guild.id}.json')
    with open(currently_playing_file, 'w') as f:
        json.dump({}, f, indent=4)

def cleanup_on_shutdown():
    """Clean up resources when the bot is shutting down"""
    for server in servers.values():
        if server['current_song']:
            server['current_song'].cleanup()
        if server['next_song']:
            server['next_song'].cleanup()
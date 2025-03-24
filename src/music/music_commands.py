import asyncio
import discord
import re
import traceback
import random

from discord.ext import commands
import yt_dlp as youtube_dl
import spotipy

from utils.helpers import save_queue, normalize_youtube_music_url
from .music_sources import ytdl, spotify, YTDLSource, ytdl_format_options
from .music_manager import (
    get_server_state, play_next, preload_next_song, 
    clear_queue_and_current_song
)

def setup_music_commands(bot):
    @bot.command(name='play', help='Plays a song or adds a playlist', aliases=['p', 'q', 'request', 'song', 'queue'])
    async def play(ctx, *, search: str):
        state = await get_server_state(ctx)
        try:
            if not ctx.message.author.voice:
                await ctx.send(f'{ctx.message.author.display_name} is not connected to a voice channel')
                return

            channel = ctx.message.author.voice.channel
            if ctx.voice_client is None:
                await channel.connect()

            search = normalize_youtube_music_url(search)

            youtube_url_pattern = re.compile(
                r'(https?://)?(www\.)?(music\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(playlist|watch)\?(.+)'
            )
            spotify_url_pattern = re.compile(r'(https?://)?(open\.)?spotify\.com/(track|playlist|album|artist)/.+')

            ytdl_options = ytdl_format_options.copy()
            ytdl_options['noplaylist'] = False
            ytdl_options['playlistend'] = 10

            first_track = True

            if youtube_url_pattern.match(search):
                url = search
                if 'playlist' in url:
                    await ctx.send('Fetching YouTube playlist metadata, this may take a moment...')

                ytdl_temp = youtube_dl.YoutubeDL(ytdl_options)
                try:
                    info = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl_temp.extract_info(url, download=False))
                except Exception as e:
                    await ctx.send(f'An error occurred: {str(e)}')
                    return

                if 'entries' in info:
                    if not info['entries']:
                        await ctx.send("The playlist is empty or could not be retrieved.")
                        return
                    for entry in info['entries']:
                        state['queue'].append({'url': entry['webpage_url'], 'title': entry['title'], 'duration': entry.get('duration', 0), 'channel': entry.get('uploader', 'Unknown')})
                        if first_track and (not ctx.voice_client.is_playing()):
                            await play_next(ctx)
                            first_track = False
                    save_queue(ctx.guild.id, state['queue'])
                    await ctx.send(f'**Added {len(info["entries"])} videos from the YouTube playlist to the queue.**')
                else:
                    try:
                        player_data = await YTDLSource.from_url(url, loop=asyncio.get_event_loop(), stream=True)
                    except Exception as e:
                        await ctx.send(f'An error occurred: {str(e)}')
                        return
                    state['queue'].append({'url': url, 'title': player_data.title, 'duration': player_data.duration, 'channel': player_data.channel})
                    save_queue(ctx.guild.id, state['queue'])
                    duration = player_data.duration if player_data.duration is not None else 0
                    await ctx.send(f'**Added to queue:** {player_data.title} [{duration//60}:{duration%60:02d}]')
                    if not ctx.voice_client.is_playing():
                        await play_next(ctx)
            elif spotify_url_pattern.match(search) and spotify:
                match = spotify_url_pattern.match(search)
                url_type = match.group(3)
                items = []

                if url_type == 'track':
                    try:
                        spotify_track = spotify.track(search)
                    except spotipy.exceptions.SpotifyException as se:
                        if se.http_status == 404:
                            await ctx.send("Spotify track not found or not accessible.")
                            return
                        else:
                            await ctx.send(f"Spotify error: {se}")
                            return
                    title = spotify_track['name']
                    artist = spotify_track['artists'][0]['name']
                    search_query = f"{title} {artist}"
                    try:
                        data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{search_query}", download=False))
                    except Exception as e:
                        await ctx.send(f'An error occurred: {str(e)}')
                        return
                    if not data or 'entries' not in data or not data['entries']:
                        await ctx.send("No results found on YouTube.")
                        return
                    first_result = data['entries'][0]
                    url = first_result['webpage_url']
                    try:
                        player_data = await YTDLSource.from_url(url, loop=asyncio.get_event_loop(), stream=True)
                    except Exception as e:
                        await ctx.send(f'An error occurred: {str(e)}')
                        return
                    state['queue'].append({'url': url, 'title': player_data.title, 'duration': player_data.duration, 'channel': player_data.channel})
                    save_queue(ctx.guild.id, state['queue'])
                    duration = player_data.duration if player_data.duration is not None else 0
                    await ctx.send(f'**Added to queue:** {player_data.title} [{duration//60}:{duration%60:02d}]')
                    if not ctx.voice_client.is_playing():
                        await play_next(ctx)
                else:
                    try:
                        if url_type == 'playlist':
                            items = spotify.playlist_tracks(search, limit=10)['items']
                            await ctx.send(f'Adding top 10 tracks from the Spotify playlist...')
                        elif url_type == 'album':
                            items = spotify.album_tracks(search, limit=10)['items']
                            await ctx.send(f'Adding top 10 tracks from the Spotify album...')
                        elif url_type == 'artist':
                            items = spotify.artist_top_tracks(search)['tracks'][:10]
                            await ctx.send(f'Adding top 10 tracks from the Spotify artist...')
                    except spotipy.exceptions.SpotifyException as se:
                        if se.http_status == 404:
                            await ctx.send("Spotify resource not found or not accessible.")
                            return
                        else:
                            await ctx.send(f"Spotify error: {se}")
                            return

                    track_count = 0
                    for item in items:
                        if url_type == 'playlist':
                            track = item['track']
                        else:
                            track = item
                        title = track['name']
                        artist_name = track['artists'][0]['name']
                        search_query = f"{title} {artist_name}"
                        try:
                            data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{search_query}", download=False))
                        except Exception as e:
                            await ctx.send(f'Skipping track "{title}" due to error: {str(e)}')
                            continue
                        if data and 'entries' in data and data['entries']:
                            first_result = data['entries'][0]
                            url = first_result['webpage_url']
                            duration_secs = track['duration_ms'] // 1000 if 'duration_ms' in track else 0
                            state['queue'].append({'url': url, 'title': track['name'], 'duration': duration_secs, 'channel': artist_name})
                            track_count += 1

                            if first_track and not ctx.voice_client.is_playing():
                                await play_next(ctx)
                                first_track = False
                    save_queue(ctx.guild.id, state['queue'])
                    await ctx.send(f'**Added {track_count} tracks from the Spotify {url_type} to the queue.**')
            else:
                data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{search}", download=False))
                if not data or 'entries' not in data or not data['entries']:
                    await ctx.send("No results found.")
                    return

                first_result = data['entries'][0]
                url = first_result['webpage_url']
                try:
                    player_data = await YTDLSource.from_url(url, loop=asyncio.get_event_loop(), stream=True)
                except Exception as e:
                    await ctx.send(f'An error occurred: {str(e)}')
                    return
                state['queue'].append({'url': url, 'title': player_data.title, 'duration': player_data.duration, 'channel': player_data.channel})
                save_queue(ctx.guild.id, state['queue'])
                duration = player_data.duration if player_data.duration is not None else 0
                await ctx.send(f'**Added to queue:** {player_data.title} [{duration//60}:{duration%60:02d}]')
                if not ctx.voice_client.is_playing():
                    await play_next(ctx)

        except Exception as e:
            traceback.print_exc()
            await ctx.send(f'An error occurred: {str(e)}')

    @bot.command(name='artist', help='Plays the top 10 songs of a specified artist from Spotify', aliases=['a'])
    async def artist_cmd(ctx, *, artist_name: str):
        if not spotify:
            await ctx.send("Spotify integration is not available.")
            return
            
        state = await get_server_state(ctx)
        try:
            if not ctx.message.author.voice:
                await ctx.send(f'{ctx.message.author.display_name} is not connected to a voice channel')
                return

            await ctx.send(f'Searching for the top 10 songs of **{artist_name}**...')

            channel = ctx.message.author.voice.channel
            if ctx.voice_client is None:
                await channel.connect()

            try:
                results = spotify.search(q='artist:' + artist_name, type='artist')
            except spotipy.exceptions.SpotifyException as se:
                if se.http_status == 404:
                    await ctx.send("No artist found with that name or not accessible.")
                    return
                else:
                    await ctx.send(f"Spotify error: {se}")
                    return

            if not results['artists']['items']:
                await ctx.send("No artist found with that name.")
                return

            artist = results['artists']['items'][0]
            try:
                top_tracks = spotify.artist_top_tracks(artist['id'], country='US')
            except spotipy.exceptions.SpotifyException as se:
                if se.http_status == 404:
                    await ctx.send("No top tracks found for this artist or not accessible.")
                    return
                else:
                    await ctx.send(f"Spotify error: {se}")
                    return

            if not top_tracks['tracks']:
                await ctx.send("No top tracks found for this artist.")
                return

            track_count = 0
            first_track = True

            for track in top_tracks['tracks']:
                title = track['name']
                artist_name = track['artists'][0]['name']
                search_query = f"{title} {artist_name}"
                try:
                    data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{search_query}", download=False))
                except Exception as e:
                    await ctx.send(f'Skipping track "{title}" due to error: {str(e)}')
                    continue

                if data and 'entries' in data and data['entries']:
                    first_result = data['entries'][0]
                    url = first_result['webpage_url']
                    duration_secs = track['duration_ms'] // 1000 if 'duration_ms' in track else 0
                    state['queue'].append({'url': url, 'title': title, 'duration': duration_secs, 'channel': artist_name})
                    track_count += 1

                    if first_track and not ctx.voice_client.is_playing():
                        await play_next(ctx)
                        first_track = False

            save_queue(ctx.guild.id, state['queue'])
            await ctx.send(f'**Added {track_count} top tracks of {artist["name"]} to the queue.**')

        except Exception as e:
            traceback.print_exc()
            await ctx.send(f'An error occurred: {str(e)}')

    @bot.command(name='playlist', help='Shows the current queue', aliases=['pl', 'list'])
    async def playlist(ctx):
        state = await get_server_state(ctx)
        guild_id = ctx.guild.id
        playlist_message = ""
        if state['current_song']:
            title = state['current_song'].data.get('title', 'Unknown')
            duration = state['current_song'].data.get('duration', 0)
            playlist_message += f"**Currently playing:** {title} [{duration//60}:{duration%60:02d}]\n\n"
        
        if state['queue'] or state['next_song']:
            total_songs = len(state['queue']) + (1 if state['next_song'] else 0)
            playlist_message += f"**Next {min(10, total_songs)} Songs ({total_songs} total):**\n"
            index_offset = 0
            if state['next_song']:
                title = state['next_song'].data.get('title', 'Unknown')
                duration = state['next_song'].data.get('duration', 0)
                playlist_message += f"1. {title} [{duration//60}:{duration%60:02d}]\n"
                index_offset = 1
            for i, item in enumerate(state['queue'][:10 - index_offset]):
                title = item.get('title', 'Unknown')
                duration = item.get('duration', 0)
                if duration is not None:
                    playlist_message += f"{i + 1 + index_offset}. {title} [{duration//60}:{duration%60:02d}]\n"
                else:
                    playlist_message += f"{i + 1 + index_offset}. {title} [Unknown duration]\n"
        else:
            if not state['current_song']:
                playlist_message = "The queue is currently empty."
        
        await ctx.send(playlist_message)

    @bot.command(name='shuffle', help='Shuffles the current queue', aliases=['sh'])
    async def shuffle(ctx):
        state = await get_server_state(ctx)

        if not state['queue'] and not state['next_song']:
            await ctx.send("The queue is currently empty.")
            return

        if state['next_song']:
            preloaded_song_data = {
                'url': state['next_song'].data['webpage_url'],
                'title': state['next_song'].data['title'],
                'duration': state['next_song'].data['duration'],
                'channel': state['next_song'].data['uploader']
            }
            state['queue'].append(preloaded_song_data)
            state['next_song'].cleanup()
            state['next_song'] = None

        random.shuffle(state['queue'])
        save_queue(ctx.guild.id, state['queue'])
        await ctx.send("The queue has been shuffled.")

        await preload_next_song(ctx)

    @bot.command(name='skip', help='Skips the current song', aliases=['n', 's', 'next'])
    async def skip(ctx):
        state = await get_server_state(ctx)
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            print("Skipping the current song...")
            await ctx.send("Skipping the current song...")
            if not ctx.voice_client.is_playing():
                await play_next(ctx)
        else:
            await ctx.send("There is no song playing right now.")

    @bot.command(name='purge', help='Clears the queue and stops the current song', aliases=['pu', 'cl', 'cls', 'clr', 'clear'])
    async def purge(ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        
        clear_queue_and_current_song(ctx)
        
        await ctx.send("The queue has been cleared, the current song has been stopped, and the currently playing file has been cleared.")

    @bot.command(name='join', help='Joins the voice channel and starts playing songs from the queue if there are any', aliases=['j', 'c', 'connect'])
    async def join(ctx):
        state = await get_server_state(ctx)
        if not ctx.message.author.voice:
            await ctx.send(f'{ctx.message.author.display_name} is not connected to a voice channel')
            return

        channel = ctx.message.author.voice.channel
        if ctx.voice_client is None:
            await channel.connect()
        else:
            if ctx.voice_client.channel != channel:
                await ctx.voice_client.move_to(channel)

        if state['queue']:
            await play_next(ctx)
        else:
            await ctx.send("The queue is currently empty.")

    @bot.command(name='leave', help='To make the bot leave the voice channel', aliases=['l', 'dc', 'disconnect', 'stop'])
    async def leave(ctx):
        voice_client = ctx.message.guild.voice_client
        if voice_client is None:
            await ctx.send("The bot is not connected to a voice channel.")
            return

        if voice_client.is_playing():
            voice_client.stop()
        await ctx.send("Leaving the voice channel.")
        await voice_client.disconnect()
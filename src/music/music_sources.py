import discord
import asyncio
import yt_dlp as youtube_dl
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
from pathlib import Path
from config.config import config, PROJECT_ROOT

# Check if YouTube cookies file exists
youtube_cookies_path = PROJECT_ROOT / 'youtube_cookies.txt'
print(f"YouTube cookies file: {'Found' if youtube_cookies_path.exists() else 'Not found'} at {youtube_cookies_path}")
from config.config import config, PROJECT_ROOT

# Use proxies from config
PROXIES = config.proxies

# YouTube DL configuration (without proxy, as we'll handle proxy rotation separately)
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'cookiefile': str(PROJECT_ROOT / 'youtube_cookies.txt'),
    # Additional options to help with 403 errors
    'geo_bypass': True,
    'geo_bypass_country': 'US',
    'extractor_retries': 3,
    'retries': 10,
    'fragment_retries': 10,
    'skip_unavailable_fragments': True,
    'concurrent_fragment_downloads': 1
}

# Print a warning if cookies file doesn't exist
if not youtube_cookies_path.exists():
    print(f"WARNING: YouTube cookies file not found at {youtube_cookies_path}. Some videos may require authentication.")

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_delay_max 5 -reconnect_on_network_error 1 -reconnect_on_http_error 404',
    'options': '-vn -bufsize 128k'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

# Initialize Spotify client if credentials are available
spotify = None
if config.spotify_credentials:
    spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=config.spotify_credentials['client_id'],
        client_secret=config.spotify_credentials['client_secret']
    ))

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, original_url, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.channel = data.get('uploader')
        self.original_url = original_url
        self.original = source

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()

        # Try proxies in rotation for HTTP 429 errors
        last_error = None
        for i, proxy in enumerate(PROXIES):  # Only try the proxies in the list, never without proxy
            try:
                # Create ytdl options with current proxy
                current_options = ytdl_format_options.copy()
                current_options['proxy'] = proxy
                
                current_ytdl = youtube_dl.YoutubeDL(current_options)
                
                # We'll attempt extraction with default format first.
                data = await loop.run_in_executor(None, lambda: current_ytdl.extract_info(url, download=not stream))
                break  # Success, exit the loop
            except youtube_dl.utils.DownloadError as e:
                last_error = e
                # If it's a 429 error and we have more proxies to try, continue to next proxy
                if "HTTP Error 429: Too Many Requests" in str(e) and i < len(PROXIES) - 1:
                    print(f"Proxy {proxy} failed with 429 error, trying next proxy...")
                    continue
                # If "Requested format not available", try without 'format' option
                elif "Requested format is not available" in str(e):
                    fallback_options = current_options.copy()
                    if 'format' in fallback_options:
                        del fallback_options['format']
                    fallback_ytdl = youtube_dl.YoutubeDL(fallback_options)
                    try:
                        data = await loop.run_in_executor(None, lambda: fallback_ytdl.extract_info(url, download=not stream))
                        break  # Success, exit the loop
                    except Exception as e2:
                        last_error = e2
                        if "HTTP Error 429: Too Many Requests" in str(e2) and i < len(PROXIES) - 1:
                            print(f"Proxy {proxy} failed with 429 error on fallback, trying next proxy...")
                            continue
                        else:
                            # If it's not a 429 error, or we've tried all proxies, raise the error
                            raise Exception(f"Could not find a suitable format. {str(e2)}")
                else:
                    if 'Sign in to confirm your age' in str(e):
                        raise Exception("This video requires age confirmation and cannot be played.")
                    elif 'Sign in to confirm you' in str(e) or 'cookies' in str(e).lower():
                        cookies_path = PROJECT_ROOT / 'youtube_cookies.txt'
                        cookies_exists = cookies_path.exists()
                        raise Exception(f"Authentication required. YouTube cookies file {'exists' if cookies_exists else 'not found'} at {cookies_path}. Please check the cookies file.")
                    else:
                        # If it's not a 429 error, or we've tried all proxies, raise the error
                        raise Exception(f"An error occurred: {str(e)}")
            except Exception as general_e:
                last_error = general_e
                # If it's not a 429 error, or we've tried all proxies, raise the error
                raise Exception(f"An error occurred: {str(general_e)}")
        else:
            # If we've exhausted all proxies and still failed
            raise Exception(f"All proxies failed. Last error: {str(last_error)}")

        if 'entries' in data:
            if not data['entries']:
                raise Exception("No entries found in the playlist.")
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data, original_url=url)

    def cleanup(self):
        try:
            self.original.cleanup()
        except Exception as e:
            print(f"Error during ffmpeg cleanup: {e}")
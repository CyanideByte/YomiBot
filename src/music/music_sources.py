import discord
import asyncio
import yt_dlp as youtube_dl
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from config.config import config

# YouTube DL configuration
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'cookiefile': 'youtube_cookies.txt',
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_on_network_error 1 -reconnect_on_http_error 404',
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

        # We'll attempt extraction with default format first.
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        except youtube_dl.utils.DownloadError as e:
            # If "Requested format not available", try without 'format' option
            if "Requested format is not available" in str(e):
                fallback_options = ytdl_format_options.copy()
                if 'format' in fallback_options:
                    del fallback_options['format']
                fallback_ytdl = youtube_dl.YoutubeDL(fallback_options)
                try:
                    data = await loop.run_in_executor(None, lambda: fallback_ytdl.extract_info(url, download=not stream))
                except Exception as e2:
                    raise Exception(f"Could not find a suitable format. {str(e2)}")
            else:
                if 'Sign in to confirm your age' in str(e):
                    raise Exception("This video requires age confirmation and cannot be played.")
                else:
                    raise Exception(f"An error occurred: {str(e)}")
        except Exception as general_e:
            raise Exception(f"An error occurred: {str(general_e)}")

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
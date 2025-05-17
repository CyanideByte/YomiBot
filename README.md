# YomiBot

A versatile Discord bot for OSRS Clan Mesa with music playback, Old School RuneScape information, and competition tracking capabilities.

## Features

### 🎵 Music Player
- Play music from YouTube and Spotify
- Queue management (add, skip, shuffle, purge)
- Support for playlists, albums, and artist top tracks
- Persistent queue across bot restarts

### 🎮 OSRS Wiki Integration
- Query information from the Old School RuneScape Wiki
- AI-powered responses using Google's Gemini API
- Image recognition for OSRS items and screenshots
- Comprehensive information about items, quests, bosses, and more

### 🏆 Competition Tracking
- Track Skill of the Week (SOTW) competitions
- Track Boss of the Week (BOTW) competitions
- Integration with Wise Old Man API

### 🌐 Web Interface
- Real-time bot status monitoring
- Current music queue display

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/CyanideByte/YomiBot.git
   cd yomibot
   ```

2. Install ffmpeg (required for music playback):
    ```bash
    # On Ubuntu/Debian
    sudo apt-get install ffmpeg

    # On macOS with Homebrew
    brew install ffmpeg

    # On Windows
    # Download from https://github.com/BtbN/FFmpeg-Builds/releases
    # Extract and add to system PATH
    ```

3. Create and activate a virtual environment:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

4. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

5. Configure the bot (see Configuration section)

6. Run the bot:
    ```bash
    python src/yomibot.py
    ```

## Configuration

YomiBot uses environment variables for configuration. Create a `.env` file in the root directory based on the provided `.env.example` template:

1. Copy the example file:
   ```bash
   cp .env.example .env
   ```

2. Edit the `.env` file and fill in your credentials:
   ```
   # Discord Bot Token (Required)
   DISCORD_BOT_TOKEN=your_discord_bot_token_here

   # Spotify API Credentials (Optional)
   SPOTIFY_CLIENT_ID=your_spotify_client_id_here
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here

   # Gemini API Key (Optional)
   GEMINI_API_KEY=your_gemini_api_key_here

   # Brave Search API Key (Optional)
   BRAVE_API_KEY=your_brave_api_key_here
   ```

### YouTube Cookies (Optional)
To play age-restricted YouTube videos, create a `youtube_cookies.txt` file in the root directory:
1. Install the [Cookie-Editor](https://cookie-editor.com/) browser extension
2. Go to YouTube and log in
3. Click the Cookie-Editor extension icon
4. Click "Export" and select "Netscape HTTP Cookie File"
5. Save the exported content as `youtube_cookies.txt` in the bot's root directory

## Usage

### Running the Bot
You can run the bot directly with Python:
```bash
python src/yomibot.py
```

Or use the provided shell script to run it in a screen session:
```bash
chmod +x start_yomibot.sh
./start_yomibot.sh
```

### Web Interface
The bot includes a web interface for monitoring its status:
1. Configure your web server to serve the `www/` directory
2. Access the interface through your web browser
3. View real-time bot status and current music queue

## Commands

### Music Commands
- `!play <song/url>` - Play a song or add to queue (aliases: `!p`, `!q`, `!request`, `!song`, `!queue`)
- `!artist <name>` - Play top 10 songs of an artist (alias: `!a`)
- `!playlist` - Show current queue (aliases: `!pl`, `!list`)
- `!shuffle` - Shuffle the queue (alias: `!sh`)
- `!skip` - Skip current song (aliases: `!n`, `!s`, `!next`)
- `!purge` - Clear the queue (aliases: `!pu`, `!cl`, `!cls`, `!clr`, `!clear`)
- `!join` - Join voice channel (aliases: `!j`, `!c`, `!connect`)
- `!leave` - Leave voice channel (aliases: `!l`, `!dc`, `!disconnect`, `!stop`)
- `!pause` - Pause playback (alias: `!ps`)
- `!resume` - Resume playback (alias: `!rs`)

### OSRS Commands
- `!askyomi <query>` - Ask a question about Old School RuneScape (aliases: `!yomi`, `!ask`)
- `!roast <username>` - Roast a player based on their OSRS stats
- `!sotw` - Display recent Skill of the Week competitions
- `!botw` - Display recent Boss of the Week competitions

### General Commands
- `!about` - Display information about the bot

## Project Structure

```
.
├── src/
│   ├── yomibot.py            # Main bot file
│   ├── config/               # Configuration handling
│   │   ├── __init__.py
│   │   └── config.py
│   ├── music/                # Music player functionality
│   │   ├── __init__.py
│   │   ├── music_commands.py
│   │   ├── music_manager.py
│   │   └── music_sources.py
│   └── osrs/                 # OSRS functionality
│       ├── __init__.py
│       ├── search.py
│       ├── wiki.py
│       ├── wiseoldman.py     # Wise Old Man API integration
│       └── llm/              # LLM functionality
│           ├── __init__.py
│           ├── chat_endpoint.py
│           ├── commands.py
│           ├── identification.py
│           ├── image_processing.py
│           ├── llm_service.py
│           ├── query_processing.py
│           └── source_management.py
├── www/                      # Web interface
│   ├── index.php
│   ├── get_current_state.php
│   ├── yomibot.png
│   ├── yomimusic.png
│   └── favicon.ico
├── .env.example             # Environment variables template
├── requirements.txt         # Python dependencies
└── start_yomibot.sh        # Startup script
```

## Dependencies

- discord.py (≥2.0.0) - Discord API wrapper
- yt-dlp (≥2023.3.4) - YouTube downloader
- spotipy (≥2.22.1) - Spotify API client
- requests (≥2.28.2) - HTTP requests
- beautifulsoup4 (≥4.11.2) - HTML parsing
- google-generativeai (≥0.3.0) - Google Gemini API client
- asyncio (≥3.4.3) - Asynchronous I/O
- python-dotenv (≥1.0.0) - Environment variable management
- PyNaCl (≥1.5.0) - Voice support
- litellm (≥1.0.0) - LLM interface

## Author

Created by CyanideByte for OSRS Clan Mesa.

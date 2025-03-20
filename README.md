# YomiBot

A versatile Discord bot for OSRS Clan Mesa with music playback, Old School RuneScape information, and competition tracking capabilities.

[![GitHub](https://img.shields.io/github/license/CyanideByte/YomiBot)](https://github.com/CyanideByte/YomiBot/blob/main/LICENSE)

## Features

### 🎵 Music Player
- Play music from YouTube and Spotify
- Queue management (add, skip, shuffle, purge)
- Support for playlists, albums, and artist top tracks
- Persistent queue across bot restarts

### 🎮 OSRS Wiki Integration
- Query information from the Old School RuneScape Wiki
- AI-powered responses using Google's Gemini API
- Comprehensive information about items, quests, bosses, and more

### 🏆 Competition Tracking
- Track Skill of the Week (SOTW) competitions
- Track Boss of the Week (BOTW) competitions
- Integration with Wise Old Man API

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/CyanideByte/YomiBot.git
   cd yomibot
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure the bot (see Configuration section)

5. Run the bot:
   ```bash
   python yomibot/yomibot.py
   ```

## Configuration

YomiBot requires several configuration files:

### Discord Bot Token
Create a file named `bot_token.txt` in the root directory with your Discord bot token.

### Spotify API Credentials (Optional)
Create a file named `spotify_credentials.txt` in the root directory with your Spotify API credentials in JSON format:
```json
{
  "client_id": "your_spotify_client_id",
  "client_secret": "your_spotify_client_secret"
}
```

### Gemini API Key (Optional)
Set the `GEMINI_API_KEY` environment variable with your Google Gemini API key:
```bash
export GEMINI_API_KEY=your_gemini_api_key
```

## Usage

### Running the Bot
You can run the bot directly with Python:
```bash
python yomibot/yomibot.py
```

Or use the provided shell script to run it in a screen session:
```bash
chmod +x start_yomibot.sh
./start_yomibot.sh
```

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

### OSRS Commands
- `!askyomi <query>` - Ask a question about Old School RuneScape

### Competition Commands
- `!sotw` - Display recent Skill of the Week competitions
- `!botw` - Display recent Boss of the Week competitions

### General Commands
- `!about` - Display information about the bot

## Project Structure

```
yomibot/
├── yomibot.py              # Main bot file
├── config/                 # Configuration handling
│   ├── __init__.py
│   └── config.py
├── music/                  # Music player functionality
│   ├── __init__.py
│   └── player.py
├── osrs/                   # OSRS Wiki integration
│   ├── __init__.py
│   └── wiki.py
├── competition/            # Competition tracking
│   ├── __init__.py
│   └── tracker.py
└── utils/                  # Utility functions
    ├── __init__.py
    └── helpers.py
```

## Dependencies

- discord.py - Discord API wrapper
- yt-dlp - YouTube downloader
- spotipy - Spotify API client
- requests - HTTP requests
- BeautifulSoup4 - HTML parsing
- google-generativeai - Google Gemini API client

## License

[MIT License](LICENSE)

## Author

Created by CyanideByte for OSRS Clan Mesa.
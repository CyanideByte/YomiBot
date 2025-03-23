import json
import os

# Configuration class to handle loading and storing bot configuration
class Config:
    def __init__(self):
        self.bot_token = None
        self.spotify_credentials = None
        self.gemini_api_key = None
        self.gemini_model = "gemini-2.0-flash"
        self.load_config()
    
    def load_config(self):
        """Load all configuration from files and environment variables"""
        self._load_bot_token()
        self._load_spotify_credentials()
        self._load_gemini_config()
    
    def _load_bot_token(self):
        """Read bot token from bot_token.txt"""
        try:
            with open('../bot_token.txt', 'r') as file:
                self.bot_token = file.read().strip()
        except FileNotFoundError:
            print("Warning: bot_token.txt not found")
            self.bot_token = None
    
    def _load_spotify_credentials(self):
        """Read Spotify credentials from spotify_credentials.txt"""
        try:
            with open('../spotify_credentials.txt', 'r') as file:
                self.spotify_credentials = json.load(file)
        except FileNotFoundError:
            print("Warning: spotify_credentials.txt not found")
            self.spotify_credentials = None
        except json.JSONDecodeError:
            print("Warning: spotify_credentials.txt contains invalid JSON")
            self.spotify_credentials = None
    
    def _load_gemini_config(self):
        """Load Gemini API configuration from environment variables"""
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        if not self.gemini_api_key:
            print("Warning: GEMINI_API_KEY environment variable is not set")

# Create a singleton instance
config = Config()
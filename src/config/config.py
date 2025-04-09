import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Get the project root directory (2 levels up from this file)
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()

# Cache directory paths
CACHE_ROOT = PROJECT_ROOT / 'cache'
WIKI_CACHE = CACHE_ROOT / 'wiki'
WOM_CACHE = CACHE_ROOT / 'wiseoldman'
PLAYERS_CACHE = WOM_CACHE / 'players'
SEARCH_CACHE = CACHE_ROOT / 'search'
PAGES_CACHE = SEARCH_CACHE / 'pages'

# Load environment variables from .env file
dotenv_path = PROJECT_ROOT / '.env'
if dotenv_path.exists():
    print(f"Loading environment variables from {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)
else:
    print(f"Warning: .env file not found at {dotenv_path}")
    # Try loading from current directory as fallback
    load_dotenv()

# Configuration class to handle loading and storing bot configuration
def ensure_cache_directories():
    """Ensure the cache directories exist"""
    os.makedirs(WIKI_CACHE, exist_ok=True)
    os.makedirs(WOM_CACHE, exist_ok=True)
    os.makedirs(PLAYERS_CACHE, exist_ok=True)
    os.makedirs(SEARCH_CACHE, exist_ok=True)
    os.makedirs(PAGES_CACHE, exist_ok=True)

class Config:
    def __init__(self):
        self.bot_token = None
        self.spotify_credentials = None
        self.gemini_api_key = None
        self.brave_api_key = None
        self.wise_old_man_api_key = None
        self.wise_old_man_user_agent = None
        self.gemini_model = "gemini-2.0-flash"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ensure_cache_directories()  # Ensure cache directories exist on startup
        self.load_config()
    
    def load_config(self):
        """Load all configuration from files and environment variables"""
        self._load_bot_token()
        self._load_spotify_credentials()
        self._load_gemini_config()
        self._load_brave_config()
        self._load_wise_old_man_config()
    
    def _load_bot_token(self):
        """Load bot token from environment variable or fallback to file"""
        self.bot_token = os.getenv('DISCORD_BOT_TOKEN')
        
        # Debug information
        print(f"DISCORD_BOT_TOKEN from environment: {'Found' if self.bot_token else 'Not found'}")
        
        # Fallback to file if environment variable is not set
        if not self.bot_token:
            print("Warning: DISCORD_BOT_TOKEN environment variable is not set")
            # Try to load from the old location as fallback
            token_file = PROJECT_ROOT / 'bot_token.txt'
            if token_file.exists():
                print(f"Attempting to load bot token from {token_file}")
                try:
                    with open(token_file, 'r') as file:
                        self.bot_token = file.read().strip()
                        print("Successfully loaded bot token from file")
                except Exception as e:
                    print(f"Error loading bot token from file: {e}")
            else:
                print(f"Bot token file not found at {token_file}")
                
        if not self.bot_token:
            print("ERROR: No bot token found. Please set DISCORD_BOT_TOKEN in your .env file")
    
    def _load_spotify_credentials(self):
        """Load Spotify credentials from environment variables or fallback to file"""
        client_id = os.getenv('SPOTIFY_CLIENT_ID')
        client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        
        # Debug information
        print(f"SPOTIFY_CLIENT_ID from environment: {'Found' if client_id else 'Not found'}")
        print(f"SPOTIFY_CLIENT_SECRET from environment: {'Found' if client_secret else 'Not found'}")
        
        if client_id and client_secret:
            self.spotify_credentials = {
                'client_id': client_id,
                'client_secret': client_secret
            }
        else:
            print("Warning: SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET environment variables are not set")
            # Try to load from the old location as fallback
            creds_file = PROJECT_ROOT / 'spotify_credentials.txt'
            if creds_file.exists():
                print(f"Attempting to load Spotify credentials from {creds_file}")
                try:
                    with open(creds_file, 'r') as file:
                        self.spotify_credentials = json.load(file)
                        print("Successfully loaded Spotify credentials from file")
                except Exception as e:
                    print(f"Error loading Spotify credentials from file: {e}")
                    self.spotify_credentials = None
            else:
                print(f"Spotify credentials file not found at {creds_file}")
                self.spotify_credentials = None
    
    def _load_gemini_config(self):
        """Load Gemini API configuration from environment variables"""
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        
        # Debug information
        print(f"GEMINI_API_KEY from environment: {'Found' if self.gemini_api_key else 'Not found'}")
        
        if not self.gemini_api_key:
            print("Warning: GEMINI_API_KEY environment variable is not set")
    
    def _load_brave_config(self):
        """Load Brave Search API configuration from environment variables"""
        self.brave_api_key = os.getenv('BRAVE_API_KEY')
        
        # Debug information
        print(f"BRAVE_API_KEY from environment: {'Found' if self.brave_api_key else 'Not found'}")
        
        if not self.brave_api_key:
            print("Warning: BRAVE_API_KEY environment variable is not set")
    
    def _load_wise_old_man_config(self):
        """Load Wise Old Man API configuration from environment variables"""
        self.wise_old_man_api_key = os.getenv('WISE_OLD_MAN_API_KEY')
        
        # Debug information
        print(f"WISE_OLD_MAN_API_KEY from environment: {'Found' if self.wise_old_man_api_key else 'Not found'}")
        
        if not self.wise_old_man_api_key:
            print("Warning: WISE_OLD_MAN_API_KEY environment variable is not set")
        
        # Also load the user agent
        self.wise_old_man_user_agent = os.getenv('WISE_OLD_MAN_USER_AGENT')
        
        # Debug information
        print(f"WISE_OLD_MAN_USER_AGENT from environment: {'Found' if self.wise_old_man_user_agent else 'Not found'}")
        
        if not self.wise_old_man_user_agent:
            print("Warning: WISE_OLD_MAN_USER_AGENT environment variable is not set")

# Create a singleton instance
config = Config()
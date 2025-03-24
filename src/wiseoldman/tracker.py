import requests
import json
import os
import time
from utils.helpers import transform_metric_name

# Replace with your clan's group ID
GROUP_ID = "3773"
BASE_URL = "https://api.wiseoldman.net/v2/groups"

def ensure_cache_directories():
    """Ensure the cache directories exist"""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    wiki_cache = os.path.join(root_dir, 'cache', 'wiki')
    wom_cache = os.path.join(root_dir, 'cache', 'wiseoldman')
    
    # Create cache directories if they don't exist
    os.makedirs(wiki_cache, exist_ok=True)
    os.makedirs(wom_cache, exist_ok=True)

# Create cache directories when module is loaded
ensure_cache_directories()

# Cache for guild members list
_guild_members_cache = {
    'data': None,
    'timestamp': 0
}

# List of OSRS skills
SKILLS = [
    "attack", "strength", "defence", "ranged", "prayer", "magic", "runecrafting",
    "construction", "hitpoints", "agility", "herblore", "thieving", "crafting",
    "fletching", "slayer", "hunter", "mining", "smithing", "fishing", "cooking",
    "firemaking", "woodcutting", "farming"
]

def get_recent_competitions(group_id):
    """
    Retrieves the most recent competitions for the group, 
    sorted by start date (most recent first).
    """
    url = f"{BASE_URL}/{group_id}/competitions"
    try:
        response = requests.get(url)
        response.raise_for_status()
        competitions = response.json()
        competitions.sort(key=lambda x: x["startsAt"], reverse=True)
        return competitions
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return []

# Register competition commands
def setup_competition_commands(bot):
    @bot.command(name='sotw', help='Displays the most recent Skill of the Week competitions.')
    async def sotw(ctx):
        """Command to print Skill Metrics (Skill of the Week)."""
        recent_competitions = get_recent_competitions(GROUP_ID)
        if not recent_competitions:
            await ctx.send("No recent competitions found or an error occurred.")
            return

        # Filter and gather the 6 most recent skill competitions
        skill_competitions = [
            comp for comp in recent_competitions if comp['metric'].lower() in SKILLS
        ][:6]

        if not skill_competitions:
            await ctx.send("No recent skill competitions found.")
            return

        # Transform the metric names for display
        skill_metrics = [transform_metric_name(comp['metric']) for comp in skill_competitions]
        await ctx.send(f"Last six skills: {', '.join(skill_metrics)}")

    @bot.command(name='botw', help='Displays the most recent Boss of the Week competitions.')
    async def botw(ctx):
        """Command to print Boss Metrics (Boss of the Week)."""
        recent_competitions = get_recent_competitions(GROUP_ID)
        if not recent_competitions:
            await ctx.send("No recent competitions found or an error occurred.")
            return

        # Filter and gather the 6 most recent boss competitions
        boss_competitions = [
            comp for comp in recent_competitions if comp['metric'].lower() not in SKILLS
        ][:6]

        if not boss_competitions:
            await ctx.send("No recent boss competitions found.")
            return

        # Transform the metric names for display
        boss_metrics = [transform_metric_name(comp['metric']) for comp in boss_competitions]
        await ctx.send(f"Last six bosses: {', '.join(boss_metrics)}")
    
    @bot.command(name='player', aliases=['lookup'], help='Displays information about a player.')
    async def player(ctx, username=None):
        """Command to display player information from Wise Old Man."""
        if username is None:
            await ctx.send("Please provide a username. Example: !player zezima")
            return
        
        player_data = fetch_player_details(username)
        if player_data:
            # Get formatted data and split into lines
            formatted_data = format_player_data(player_data).split('\n')
            current_chunk = []
            current_length = 0

            for line in formatted_data:
                # Account for the length of line, newline, and Discord markdown (```\n and \n```)
                line_length = len(line) + 1  # +1 for newline
                if current_length + line_length > 1900:
                    # Send current chunk if adding this line would exceed limit
                    if current_chunk:
                        await ctx.send(f"```\n{'\n'.join(current_chunk)}\n```")
                        current_chunk = []
                        current_length = 0
                
                current_chunk.append(line)
                current_length += line_length

            # Send any remaining lines
            if current_chunk:
                await ctx.send(f"```\n{'\n'.join(current_chunk)}\n```")
        else:
            await ctx.send(f"Could not find player '{username}' or an error occurred.")

def get_guild_members():
    """
    Returns a list of guild member names.
    If the cache is less than an hour old, returns cached data.
    Otherwise, fetches fresh data from the API.
    """
    import time
    current_time = time.time()
    cache_age = current_time - _guild_members_cache['timestamp']
    
    # If cache is valid (less than 1 hour old) and contains data
    if _guild_members_cache['data'] is not None and cache_age < 3600:
        return _guild_members_cache['data']
        
    # Fetch fresh data from API
    try:
        response = requests.get(f"{BASE_URL}/{GROUP_ID}/csv")
        response.raise_for_status()
        
        # Split into lines and skip header row
        lines = response.text.strip().split('\n')[1:]
        # Extract just the Player names (first column)
        members = [line.split(',')[0] for line in lines]
        
        # Update cache
        _guild_members_cache['data'] = members
        _guild_members_cache['timestamp'] = current_time
        
        return members
    except requests.exceptions.RequestException as e:
        print(f"Error fetching guild members: {e}")
        # If we have cached data, return it even if expired
        if _guild_members_cache['data'] is not None:
            print("Returning expired cached data due to API error")
            return _guild_members_cache['data']
        return []

def get_player_cache_path(username):
    """Get the cache file path for a given player name"""
    # Normalize the username - lowercase and replace spaces with underscores
    safe_name = username.lower().replace(' ', '_')
    # Use project root directory for cache folder
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(root_dir, 'cache', 'wiseoldman', f"{safe_name}.json")

def fetch_player_details(username):
    """
    Fetch player details from the WiseOldMan API with caching
    """
    cache_path = get_player_cache_path(username)
    current_time = time.time()
    
    # Check for cached data first
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            # Check if cache is less than 1 hour old
            cache_age = current_time - cache_data.get('timestamp', 0)
            if cache_age < 3600:  # 1 hour in seconds
                print(f"Using cached data for player {username} (less than 1 hour old)")
                return cache_data.get('player_data')
            else:
                print(f"Cache for player {username} is older than 1 hour, fetching fresh data")
        except Exception as e:
            print(f"Error reading cache for {username}: {e}")
    
    # If no valid cache exists, fetch from API
    url = f"https://api.wiseoldman.net/v2/players/{username}"
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for non-200 status codes
        player_data = response.json()
        
        # Save to cache
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump({
                'player_data': player_data,
                'timestamp': current_time
            }, f, ensure_ascii=False)
        
        return player_data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching player details: {e}")
        return None

def format_player_data(player_data):
    """
    Format player data into a single string for display
    """
    if not player_data:
        return f"Could not fetch player data"
    
    output = []
    
    # Player basic info
    output.append(f"Player: {player_data.get('displayName', 'N/A')}")
    output.append(f"Combat Level: {player_data.get('combatLevel', 'N/A')}")
    output.append(f"Total Experience: {player_data.get('exp', 'N/A')}")
    output.append(f"Last Updated: {player_data.get('updatedAt', 'N/A')}")
    output.append("")
    
    # Skills data
    if 'latestSnapshot' in player_data and 'data' in player_data['latestSnapshot']:
        skills_data = player_data['latestSnapshot']['data']['skills']
        
        output.append("===== SKILL LEVELS =====")
        output.append(f"{'Skill':<15} {'Level':<10} {'Experience':<15}")
        output.append("-" * 40)
        
        for skill_name, skill_info in skills_data.items():
            if skill_info['level'] > 0:  # Only show skills with levels
                output.append(f"{skill_name.capitalize():<15} {skill_info['level']:<10} {skill_info['experience']:<15}")
        
        output.append("")
        
        # Boss kills data
        bosses_data = player_data['latestSnapshot']['data']['bosses']
        
        output.append("===== BOSS KILL COUNTS =====")
        output.append(f"{'Boss':<25} {'Kills':<10}")
        output.append("-" * 35)
        
        for boss_name, boss_info in bosses_data.items():
            # Only show bosses with kills
            if boss_info['kills'] > 0:
                boss_display_name = boss_name.replace('_', ' ').title()
                if boss_display_name == "Chambers Of Xeric Challenge Mode":
                    boss_display_name = "Chambers Of Xeric (CM)"
                output.append(f"{boss_display_name:<25} {boss_info['kills']:<10}")
    else:
        output.append("No skill or boss data available")
    
    # Join all lines with newlines and return
    return "\n".join(output)

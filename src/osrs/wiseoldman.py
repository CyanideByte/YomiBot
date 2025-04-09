import json
import os
import time
import asyncio
import aiohttp
import requests
from config.config import PROJECT_ROOT, config, PLAYERS_CACHE

# Replace with your clan's group ID
GROUP_ID = "3773"
BASE_URL = "https://api.wiseoldman.net/v2/groups"

# Cache for guild members list
_guild_members_cache = {
    'data': None,
    'lastCachedTime': '1970-01-01T00:00:00.000Z'
}

# List of OSRS skills
SKILLS = [
    "attack", "strength", "defence", "ranged", "prayer", "magic", "runecrafting",
    "construction", "hitpoints", "agility", "herblore", "thieving", "crafting",
    "fletching", "slayer", "hunter", "mining", "smithing", "fishing", "cooking",
    "firemaking", "woodcutting", "farming"
]

def transform_metric_name(metric):
    """
    Removes 'the_' prefix if present and capitalizes the metric words.
    """
    if metric.startswith("the_"):
        metric = metric[4:]
    return " ".join(word.capitalize() for word in metric.split("_"))

def get_recent_competitions(group_id):
    """
    Retrieves the most recent competitions for the group, 
    sorted by start date (most recent first).
    """
    url = f"{BASE_URL}/{group_id}/competitions"
    try:
        response = requests.get(url, headers={"User-Agent": config.user_agent})
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
    
    # Player command has been moved to llm.py as a roast command

def get_guild_members():
    """
    Returns a list of guild member names.
    If the cache is less than an hour old, returns cached data.
    Otherwise, fetches fresh data from the API.
    """
    import time
    last_cached = time.strptime(_guild_members_cache['lastCachedTime'], '%Y-%m-%dT%H:%M:%S.000Z')
    cache_age = time.mktime(time.gmtime()) - time.mktime(last_cached)
    
    # If cache is valid (less than 1 hour old) and contains data
    if _guild_members_cache['data'] is not None and cache_age < 3600:
        return _guild_members_cache['data']
        
    # Fetch fresh data from API
    try:
        response = requests.get(f"{BASE_URL}/{GROUP_ID}/csv", headers={"User-Agent": config.user_agent})
        response.raise_for_status()
        
        # Split into lines and skip header row
        lines = response.text.strip().split('\n')[1:]
        # Extract just the Player names (first column)
        members = [line.split(',')[0] for line in lines]
        
        # Update cache
        _guild_members_cache['data'] = members
        _guild_members_cache['lastCachedTime'] = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
        
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
    # Use players cache directory
    return os.path.join(PLAYERS_CACHE, f"{safe_name}.json")

async def fetch_player_details(username, session=None):
    """
    Fetch player details from the WiseOldMan API with caching
    
    Args:
        username: The username to fetch details for
        session: Optional aiohttp ClientSession. If not provided, a new one will be created
    """
    # Replace spaces with underscores for API request
    api_username = username.replace(' ', '_')
    
    cache_path = get_player_cache_path(username)
    current_time = time.time()
    
    # Check for cached data first
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            # Check if cache is less than 1 hour old
            last_cached = time.strptime(cache_data.get('lastFileCachedTime', '1970-01-01T00:00:00.000Z'), '%Y-%m-%dT%H:%M:%S.000Z')
            cache_age = time.mktime(time.gmtime()) - time.mktime(last_cached)
            if cache_age < 3600:  # 1 hour in seconds
                print(f"Using cached data for player {username} (less than 1 hour old)")
                return cache_data.get('player_data')
            else:
                print(f"Cache for player {username} is older than 1 hour, fetching fresh data")
        except Exception as e:
            print(f"Error reading cache for {username}: {e}")
    
    # If no valid cache exists, fetch from API
    url = f"https://api.wiseoldman.net/v2/players/{api_username}"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": config.user_agent
    }
    
    try:
        should_close_session = False
        if session is None:
            session = aiohttp.ClientSession()
            should_close_session = True
            
        try:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()  # Raise an exception for non-200 status codes
                player_data = await response.json()
                
                # Save to cache
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        'player_data': player_data,
                        'lastFileCachedTime': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
                    }, f, ensure_ascii=False)
                
                return player_data
        finally:
            if should_close_session:
                await session.close()
                
    except Exception as e:
        print(f"Error fetching player details for {username}: {e}")
        return None


def format_player_data(player_data):
    """
    Format player data into a single string for display
    """
    if not player_data:
        return f"Could not fetch player data"
    
    output = []
    
    
    player_name = player_data.get('displayName', 'N/A')

    # Add Source URL
    source_url = f"https://wiseoldman.net/players/{player_name.lower().replace(' ', '_')}"
    output.append(f"Source URL: {source_url}")
    output.append("")
    
    # Player basic info
    output.append(f"Player: {player_name}")
    output.append(f"Combat Level: {player_data.get('combatLevel', 'N/A')}")
    output.append(f"Total Experience: {player_data.get('exp', 'N/A')}")
    
    # Check if we have all required data
    if not ('latestSnapshot' in player_data and
            player_data['latestSnapshot'] is not None and
            'data' in player_data['latestSnapshot'] and
            player_data['latestSnapshot']['data'] is not None and
            'skills' in player_data['latestSnapshot']['data'] and
            player_data['latestSnapshot']['data']['skills'] is not None and
            'bosses' in player_data['latestSnapshot']['data'] and
            player_data['latestSnapshot']['data']['bosses'] is not None):
        return None  # Return None if any required data is missing

    # If we have all required data, proceed with formatting
    skills_data = player_data['latestSnapshot']['data']['skills']
    
    output.append("===== SKILL LEVELS =====")
    output.append(f"{'Skill':<15} {'Level':<10} {'Experience':<15}")
    output.append("-" * 40)
    
    for skill_name, skill_info in skills_data.items():
        # Show all skills, and convert -1 values to 0
        level = skill_info['level'] if skill_info['level'] != -1 else 1
        experience = skill_info['experience'] if skill_info['experience'] != -1 else 0
        output.append(f"{skill_name.capitalize():<15} {level:<10} {experience:<15}")
    
    output.append("")
    
    # Boss kills data
    bosses_data = player_data['latestSnapshot']['data']['bosses']
    
    output.append("===== BOSS KILL COUNTS =====")
    output.append(f"{'Boss':<25} {'Kills':<10}")
    output.append("-" * 35)
    
    for boss_name, boss_info in bosses_data.items():
        # Show all bosses, and convert -1 values to 0
        kills = boss_info['kills'] if boss_info['kills'] != -1 else 0
        boss_display_name = boss_name.replace('_', ' ').title()
        if boss_display_name == "Chambers Of Xeric Challenge Mode":
            boss_display_name = "Chambers Of Xeric (CM)"
        output.append(f"{boss_display_name:<25} {kills:<10}")
    
    # Join all lines with newlines and return
    return "\n".join(output)
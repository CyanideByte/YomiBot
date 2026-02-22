import json
import os
from datetime import datetime, timezone, timedelta
import asyncio
import aiohttp
import requests
from config.config import PROJECT_ROOT, config, PLAYERS_CACHE, WOM_CACHE, METRICS_CACHE

# Replace with your clan's group ID
GROUP_ID = "3773"
BASE_URL = "https://api.wiseoldman.net/v2"

def get_guild_cache_path():
    """Get the cache file path for guild members"""
    return os.path.join(WOM_CACHE, "guild_members.json")
# List of OSRS skills
SKILLS = [
    "attack", "strength", "defence", "ranged", "prayer", "magic", "runecrafting",
    "construction", "hitpoints", "agility", "herblore", "thieving", "crafting",
    "fletching", "slayer", "hunter", "mining", "smithing", "fishing", "cooking",
    "firemaking", "woodcutting", "farming", "sailing"
]

# Predefined metric names for OSRS
SKILL_METRICS = [
    'overall', 'attack', 'defence', 'strength', 'hitpoints', 'ranged', 'prayer', 'magic',
    'cooking', 'woodcutting', 'fletching', 'fishing', 'firemaking', 'crafting', 'smithing',
    'mining', 'herblore', 'agility', 'thieving', 'slayer', 'farming', 'runecrafting',
    'hunter', 'construction'
]

ACTIVITY_METRICS = [
    'league_points', 'bounty_hunter_hunter', 'bounty_hunter_rogue', 'clue_scrolls_all',
    'clue_scrolls_beginner', 'clue_scrolls_easy', 'clue_scrolls_medium', 'clue_scrolls_hard',
    'clue_scrolls_elite', 'clue_scrolls_master', 'last_man_standing', 'pvp_arena',
    'soul_wars_zeal', 'guardians_of_the_rift', 'colosseum_glory', 'collections_logged'
]

BOSS_METRICS = [
    'abyssal_sire', 'alchemical_hydra', 'amoxliatl', 'araxxor', 'artio', 'barrows_chests',
    'bryophyta', 'callisto', 'calvarion', 'cerberus', 'chambers_of_xeric',
    'chambers_of_xeric_challenge_mode', 'chaos_elemental', 'chaos_fanatic', 'commander_zilyana',
    'corporeal_beast', 'crazy_archaeologist', 'dagannoth_prime', 'dagannoth_rex',
    'dagannoth_supreme', 'deranged_archaeologist', 'duke_sucellus', 'general_graardor',
    'giant_mole', 'grotesque_guardians', 'hespori', 'kalphite_queen', 'king_black_dragon',
    'kraken', 'kreearra', 'kril_tsutsaroth', 'lunar_chests', 'mimic', 'nex', 'nightmare',
    'phosanis_nightmare', 'obor', 'phantom_muspah', 'sarachnis', 'scorpia', 'scurrius',
    'skotizo', 'sol_heredit', 'spindel', 'tempoross', 'the_gauntlet', 'the_corrupted_gauntlet',
    'the_hueycoatl', 'the_leviathan', 'the_royal_titans', 'the_whisperer', 'theatre_of_blood',
    'theatre_of_blood_hard_mode', 'thermonuclear_smoke_devil', 'tombs_of_amascut',
    'tombs_of_amascut_expert', 'tzkal_zuk', 'tztok_jad', 'vardorvis', 'venenatis', 'vetion',
    'vorkath', 'wintertodt', 'yama', 'zalcano', 'zulrah'
]

TYPE_MAPPING = {
        "regular": "Main",
        "ironman": "Ironman",
        "hardcore": "Hardcore Ironman"
    }

# Combine all metrics for validation
ALL_METRICS = SKILL_METRICS + ACTIVITY_METRICS + BOSS_METRICS

def transform_metric_name(metric):
    """
    Removes 'the_' prefix if present and capitalizes the metric words.
    """
    if metric.startswith("the_"):
        metric = metric[4:]
    return " ".join(word.capitalize() for word in metric.split("_"))

def fetch_metric(metric: str):
    """
    Fetches scoreboard data for a given metric and returns a list of key-value pairs
    with player names and values. Uses caching to reduce API calls.
    
    Args:
        metric (str): The metric to fetch data for (e.g., 'chambers_of_xeric', 'fishing', etc.)
        
    Returns:
        list: List of dictionaries with 'name' and 'value' keys
    """
    # Create cache path for this metric
    cache_path = os.path.join(METRICS_CACHE, f"{metric}.json")
    
    # Check for cached data first
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            # Check if cache is less than 15 minutes old
            last_cached_str = cache_data.get('lastCachedTime', '1970-01-01T00:00:00.000Z')
            last_cached_dt = datetime.strptime(last_cached_str, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
            current_dt = datetime.now(timezone.utc)
            
            if current_dt - last_cached_dt < timedelta(minutes=15):
                print(f"Using cached data for metric {metric} (less than 15 minutes old)")
                return cache_data.get('scoreboard', [])
        except Exception as e:
            print(f"Error reading cache for metric {metric}: {e}")
    
    # If no valid cache exists, fetch from API
    print("[API CALL: WOM] group metrics")
    url = f"{BASE_URL}/groups/{GROUP_ID}/hiscores?metric={metric}&limit=500"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": config.wise_old_man_user_agent or config.user_agent
    }
    
    if config.wise_old_man_api_key:
        headers["x-api-key"] = config.wise_old_man_api_key

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    print(f"Successfully fetched data for metric: {metric}")
    
    data = response.json()
    possible_keys = ["kills", "level", "score", "value"]
    
    scoreboard = []
    for entry in data:
        player_name = entry["player"]["displayName"]
        value = None
        key_used = None
        for key in possible_keys:
            if key in entry["data"]:
                value = entry["data"][key]
                key_used = key
                break
        
        # Handle unset values (-1)
        if value == -1:
            if key_used == "level":
                value = 1  # Use 1 for unset level values
            else:
                value = 0  # Use 0 for all other unset values
        
        if value is not None:
            scoreboard.append({"name": player_name, "value": value})
    
    scoreboard = sorted(scoreboard, key=lambda x: x["value"], reverse=True)
    
    # Save to cache
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump({
            'scoreboard': scoreboard,
            'lastCachedTime': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        }, f, ensure_ascii=False)
    
    return scoreboard

def get_recent_competitions(group_id):
    """
    Retrieves the most recent competitions for the group, 
    sorted by start date (most recent first).
    """
    print("[API CALL: WOM] group competitions")
    url = f"{BASE_URL}/groups/{group_id}/competitions"
    try:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": config.wise_old_man_user_agent or config.user_agent
        }
        
        if config.wise_old_man_api_key:
            headers["x-api-key"] = config.wise_old_man_api_key

        response = requests.get(url, headers=headers)
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

def get_guild_members_data():
    """
    Returns the guild's membership data from the WiseOldMan API.
    If the cache is less than an hour old, returns cached data.
    Otherwise, fetches fresh data from the API.
    
    Returns:
        list: A list of membership objects containing player data
    """
    cache_path = get_guild_cache_path()
    
    # Check for cached data first
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            # Check if cache is less than 15 minutes old
            last_cached_str = cache_data.get('lastCachedTime', '1970-01-01T00:00:00.000Z')
            # Parse the UTC timestamp string
            last_cached_dt = datetime.strptime(last_cached_str, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
            current_dt = datetime.now(timezone.utc)
            if current_dt - last_cached_dt < timedelta(minutes=15):
                # print(f"Using cached guild members list (less than 15 minutes old)")
                return cache_data.get('memberships')
            else:
                print(f"Guild members cache is older than 15 minutes, fetching fresh data")
        except Exception as e:
            print(f"Error reading guild members cache: {e}")
    
    # Fetch fresh data from API
    try:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": config.wise_old_man_user_agent or config.user_agent
        }
        
        if config.wise_old_man_api_key:
            headers["x-api-key"] = config.wise_old_man_api_key
        
        print("[API CALL: WOM] group list members data")
        response = requests.get(f"{BASE_URL}/groups/{GROUP_ID}", headers=headers)
        response.raise_for_status()
        group_data = response.json()
        
        memberships = group_data.get('memberships', [])
        
        # Save to cache
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump({
                'memberships': memberships,
                'lastCachedTime': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            }, f, ensure_ascii=False)
        
        return memberships
    except requests.exceptions.RequestException as e:
        print(f"Error fetching guild members: {e}")
        # If we have cached data, return it even if expired
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    print("Returning expired cached data due to API error")
                    return cache_data.get('memberships', [])
            except Exception as e:
                print(f"Error reading expired cache: {e}")
        return []

def get_guild_member_by_name(username):
    """
    Returns guild member data for a specific username.
    Search is case-insensitive.
    
    Args:
        username (str): The username to search for
        
    Returns:
        dict: The member data if found, None if not found
    """
    memberships = get_guild_members_data()
    for member in memberships:
        if member['player']['displayName'].lower() == username.lower():
            return member
    return None

def get_guild_members_names():
    """
    Returns a list of guild member display names.
    Uses get_guild_members_data() but extracts only the display names.
    
    Returns:
        list: A list of member display names
    """
    memberships = get_guild_members_data()
    return [member['player']['displayName'] for member in memberships]

def get_player_cache_path(username):
    """Get the cache file path for a given player name"""
    # Normalize the username - lowercase and replace spaces with underscores
    safe_name = username.lower().replace(' ', '_')
    # Use players cache directory
    return os.path.join(PLAYERS_CACHE, f"{safe_name}.json")

async def fetch_player_details(player, session=None):
    """
    Fetch player details from the WiseOldMan API with caching
    
    Args:
        player: Player object containing displayName and other details
        session: Optional aiohttp ClientSession. If not provided, a new one will be created
    """
    username = player['displayName']
    # Replace spaces with underscores for API request
    api_username = username.replace(' ', '_')
    
    cache_path = get_player_cache_path(username)
    
    # Check for cached data first
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            # Check if essential cache keys exist
            if 'lastFileCachedTime' not in cache_data:
                 print(f"Cache file for {username} is missing 'lastFileCachedTime', fetching fresh data.")
            elif 'player_data' not in cache_data:
                print(f"Cache file for {username} is missing 'player_data', fetching fresh data.")
            else:
                cached_data = cache_data['player_data']
                current_updated = player.get('updatedAt')
                current_changed = player.get('lastChangedAt')

                # Check if we have current dates from input AND cached dates exist
                if current_updated and current_changed and \
                   'updatedAt' in cached_data and 'lastChangedAt' in cached_data:
                    
                    cached_updated = cached_data['updatedAt']
                    cached_changed = cached_data['lastChangedAt']
                    
                    try:
                        # Parse dates into datetime objects for comparison
                        # Use fromisoformat for robustness
                        cached_updated_dt = datetime.fromisoformat(cached_updated) # Use standard fromisoformat
                        cached_changed_dt = datetime.fromisoformat(cached_changed) # Use standard fromisoformat
                        current_updated_dt = datetime.fromisoformat(current_updated) # Use standard fromisoformat
                        current_changed_dt = datetime.fromisoformat(current_changed) # Use standard fromisoformat

                        # Compare dates
                        if current_updated_dt <= cached_updated_dt and current_changed_dt <= cached_changed_dt:
                            print(f"Using cached data for player {username} (no updates available based on timestamps)")
                            return cached_data
                        else:
                            print(f"Cached data for {username} is outdated based on timestamps.")
                            
                    except (ValueError, TypeError) as date_err:
                        # If there's any issue parsing dates, fetch fresh data to be safe
                        print(f"Error parsing cache dates for {username}: {date_err}. Fetching fresh data.")
                else:
                    # Missing necessary date info either from input or cache
                    if not (current_updated and current_changed):
                         print(f"Missing current update/change times for {username} in input, cannot validate cache by date.")
                    else:
                         print(f"Cache file for {username} is missing 'updatedAt' or 'lastChangedAt', fetching fresh data.")
            
            # If we reach here, cache was invalid or missing keys
            
            print(f"Updates available for player {username}, fetching fresh data")
        except Exception as e:
            print(f"Error reading cache for {username}: {e}")
    
    # If no valid cache exists, fetch from API
    print("[API CALL: WOM] get player details")
    url = f"{BASE_URL}/players/{api_username}"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": config.wise_old_man_user_agent or config.user_agent
    }
    
    if config.wise_old_man_api_key:
        headers["x-api-key"] = config.wise_old_man_api_key
    
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
                    'lastFileCachedTime': datetime.now(timezone.utc).isoformat() # Use standard isoformat
                }, f, ensure_ascii=False)
            
            return player_data
    except aiohttp.ClientResponseError as e:
        # Catch specific response errors
        print(f"HTTP Error fetching player details for {username}: {e.status} {e.message}")
        # Fall through to stale cache handling
    except Exception as e:
        print(f"Error fetching player details for {username}: {e}")
        # Fall through to stale cache handling
    finally:
        if should_close_session:
            await session.close()
            
    # Try to return stale cache data if available for any error
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            print(f"Returning stale cache for {username} due to API error.")
            return cache_data.get('player_data')
        except Exception as cache_err:
            print(f"Error reading stale cache for {username}: {cache_err}")
    return None


async def fetch_player_details_by_username(username: str, guild_member_list=None, session=None):
    """
    Fetch player details from the WiseOldMan API using only the username.
    Uses timestamp-based caching for guild members and time-based caching for non-members.

    Args:
        username (str): The player's username.
        guild_member_list (list, optional): List of guild member data to check if player is a member.
        session (aiohttp.ClientSession, optional): If not provided, a new one will be created.

    Returns:
        dict or None: Player data dictionary if found, otherwise None.
    """
    # Check if player is in guild_member_list
    current_player_obj = None
    if guild_member_list:
        for member in guild_member_list:
            if member['player']['displayName'].lower() == username.lower():
                current_player_obj = member['player']
                break
    # Replace spaces with underscores for API request and cache path
    api_username = username.replace(' ', '_')
    cache_path = get_player_cache_path(username)
    cache_duration = timedelta(hours=1) # Cache duration of 1 hour

    # Check for cached data
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            # Check for essential cache keys
            if 'lastFileCachedTime' not in cache_data:
                print(f"Cache file for {username} is missing 'lastFileCachedTime', fetching fresh data.")
            elif 'player_data' not in cache_data:
                print(f"Cache file for {username} is missing 'player_data', fetching fresh data.")
            else:
                cached_data = cache_data['player_data']
                need_fresh_data = False

                # If player is a guild member, try timestamp-based caching first
                if current_player_obj and \
                   'updatedAt' in cached_data and 'lastChangedAt' in cached_data and \
                   'updatedAt' in current_player_obj and 'lastChangedAt' in current_player_obj:

                    try:
                        # Parse dates and compare
                        cached_updated = datetime.fromisoformat(cached_data['updatedAt'])
                        cached_changed = datetime.fromisoformat(cached_data['lastChangedAt'])
                        current_updated = datetime.fromisoformat(current_player_obj['updatedAt'])
                        current_changed = datetime.fromisoformat(current_player_obj['lastChangedAt'])

                        if current_updated <= cached_updated and current_changed <= cached_changed:
                            print(f"Using cached data for guild member {username} (no updates available)")
                            return cached_data

                        print(f"Updates available for guild member {username}, fetching fresh data")
                        need_fresh_data = True

                    except (ValueError, TypeError) as e:
                        print(f"Error comparing timestamps for {username}: {e}, falling back to time-based cache")

                # Only do time-based cache check if we haven't determined we need fresh data
                if not need_fresh_data:
                    try:
                        last_cached_dt = datetime.fromisoformat(cache_data['lastFileCachedTime'])
                        current_dt = datetime.now(timezone.utc)

                        if current_dt - last_cached_dt < cache_duration:
                            print(f"Using cached data for {username} (less than {cache_duration} old)")
                            return cached_data

                        print(f"Cache for {username} is older than {cache_duration}, fetching fresh data")
                    except ValueError as e:
                        print(f"Error parsing cache timestamp for {username}: {e}, fetching fresh data")

        except Exception as e:
            print(f"Error reading cache for {username}: {e}. Fetching fresh data.")
            
    # 2. If no valid cache exists, fetch from API
    print("[API CALL: WOM] get player details")
    url = f"{BASE_URL}/players/{api_username}"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": config.wise_old_man_user_agent or config.user_agent
    }

    if config.wise_old_man_api_key:
        headers["x-api-key"] = config.wise_old_man_api_key

    should_close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        should_close_session = True

    try:
        print(f"Fetching fresh data for player {username} from API.")
        async with session.get(url, headers=headers) as response:
            if response.status == 404:
                print(f"Player {username} not found on WiseOldMan (404).")
                return None # Player not found is not an error, just return None

            response.raise_for_status()  # Raise an exception for other non-200 status codes
            player_data = await response.json()

            # 3. Save to cache
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            cache_content = {
                'player_data': player_data,
                'lastFileCachedTime': datetime.now(timezone.utc).isoformat() # Use standard isoformat
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_content, f, ensure_ascii=False)
            print(f"Saved fresh data for player {username} to cache.")

            return player_data

    except aiohttp.ClientResponseError as e:
        # Catch specific response errors after checking 404
        print(f"HTTP Error fetching player details for {username}: {e.status} {e.message}")
        # Fall through to stale cache handling
    except Exception as e:
        print(f"Generic Error fetching player details for {username}: {e}")
        # Fall through to stale cache handling
    finally:
        if should_close_session:
            await session.close()
        
    # Try to return stale cache data if available for any error
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            print(f"Returning stale cache for {username} due to API error.")
            return cache_data.get('player_data')
        except Exception as cache_err:
            print(f"Error reading stale cache for {username}: {cache_err}")
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

    account_type = player_data.get('type', 'N/A')
    mapped_type = TYPE_MAPPING.get(account_type, 'Unknown')
    
    # Player basic info
    output.append(f"Player: {player_name}")
    output.append(f"Account type: {mapped_type}")
    output.append(f"Combat Level: {player_data.get('combatLevel', 'N/A')}")
    output.append(f"Total Experience: {player_data.get('exp', 'N/A')}")
    
    # Check if we have all required data
    if not ('latestSnapshot' in player_data and
            player_data['latestSnapshot'] is not None and
            'data' in player_data['latestSnapshot'] and
            player_data['latestSnapshot']['data'] is not None):
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
    
    # Activities data
    activities_data = player_data['latestSnapshot']['data']['activities']
    
    output.append("===== ACTIVITIES =====")
    output.append(f"{'Activity':<25} {'Score':<10}")
    output.append("-" * 35)
    
    for activity_name, activity_info in activities_data.items():
        # Show all activities, and convert -1 values to 0
        score = activity_info['score'] if activity_info['score'] != -1 else 0
        activity_display_name = activity_name.replace('_', ' ').title()
        output.append(f"{activity_display_name:<25} {score:<10}")
    
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

def format_metrics(metrics_data):
    """
    Format metrics data into a text list of each player and their metrics.
    
    Args:
        metrics_data (dict): Dictionary mapping metric names to their scoreboard data
        
    Returns:
        str: Formatted text with player metrics
    """
    if not metrics_data:
        return "No metrics data available."
    
    output = []
    
    # Add header
    # Use length of first metric's scoreboard for member count
    member_count = len(next(iter(metrics_data.values()))) if metrics_data else 0
    output.append(f"CLAN METRICS FOR {member_count} MEMBERS")
    
    # Process each metric
    for metric_name, scoreboard in metrics_data.items():
        # Transform the metric name for display (e.g., "chambers_of_xeric" -> "Chambers Of Xeric")
        display_name = transform_metric_name(metric_name)
        output.append(f"\n**{display_name}**")
        
        # Add player data for this metric
        for i, entry in enumerate(scoreboard):  # Include all players
            member = get_guild_member_by_name(entry["name"])
            type = TYPE_MAPPING.get(member['player']['type'], 'Unknown')
            player_name = "(" + type + ") " + entry["name"]
            value = entry["value"]
            
            # Format the value based on the metric type
            if metric_name in SKILL_METRICS:
                # For skills, show level
                formatted_value = f"Level {value}"
            elif "kills" in str(value).lower() or metric_name in BOSS_METRICS:
                # For boss metrics, show KC
                formatted_value = f"{value} KC"
            else:
                # For other metrics, just show the value
                formatted_value = str(value)
            
            # Add rank number and format the line in a simple format
            output.append(f"{i+1}. {player_name}: {formatted_value}")
        
    # Join all lines with newlines and return
    return "\n".join(output)
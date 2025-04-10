import asyncio
import datetime
import aiohttp
import google.generativeai as genai
from config.config import config
from osrs.llm.image_processing import fetch_image, identify_items_in_images
from osrs.wiseoldman import get_guild_members, get_guild_member_names, fetch_player_details, fetch_metric

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
    'vorkath', 'wintertodt', 'zalcano', 'zulrah'
]

# Combine all metrics for validation
ALL_METRICS = SKILL_METRICS + ACTIVITY_METRICS + BOSS_METRICS

async def identify_wiki_pages(user_query: str, image_urls: list[str] = None):
    """Use Gemini to identify relevant wiki pages for the query"""
    if not config.gemini_api_key:
        print("Gemini API key not set")
        return []
    
    try:
        model = genai.GenerativeModel(config.gemini_model)
        
        # Stage 1: Process images if present
        identified_items = []
        if image_urls:
            # Download and convert images to PIL format
            images = []
            for url in image_urls:
                try:
                    image = await fetch_image(url)
                    images.append(image)
                except Exception as e:
                    print(f"Error processing image {url}: {e}")
                    continue

            if images:
                identified_items = await identify_items_in_images(images)
                print(f"Items identified in images: {identified_items}")
                if identified_items:
                    # Add identified items to user query
                    user_query = f"{user_query}\nItems in images: {', '.join(identified_items)}"

        # Stage 2: Process query (now including identified items if any)
        prompt = f"""
        You are an assistant that helps determine which Old School RuneScape (OSRS) wiki pages to fetch based on user queries.

        Important Rules:
        1. ONLY include pages that are EXPLICITLY mentioned in the query or identified from images
        2. Do NOT guess or infer related pages unless absolutely certain
        3. For items, use exact names with underscores (e.g., "Dragon_scimitar")
        4. For NPCs/bosses, include their Strategies page if available
        5. For skill pages, include their Training page
        6. When the user refers to Chambers of Xeric or CoX, also include the page Ancient_chest
        7. When the user refers to Theatre of Blood or ToB, also include the page Monumental_chest
        8. When the user refers to Tombs of Amascut or ToA, also include the page Chest_(Tombs_of_Amascut)
        9. If you cannot determine any wiki pages from the query, respond ONLY with "[NO_PAGES_FOUND]"

        Query: {user_query}
        
        Respond ONLY with page names separated by commas. No additional text. MAXIMUM 5 most important pages
        Example: "Dragon_scimitar,Abyssal_whip"
        If no pages can be determined, respond with: "[NO_PAGES_FOUND]"
        """
        
        generation = await asyncio.to_thread(
            lambda: model.generate_content(prompt)
        )
        response_text = generation.text.strip()
        
        # Check if the response indicates no pages were found
        if response_text == "[NO_PAGES_FOUND]":
            print("Identified wiki pages: []")
            return []
            
        # Normalize page names to use underscores
        page_names = [name.strip().replace(' ', '_') for name in response_text.split(',') if name.strip()][:5]
        print(f"Identified wiki pages: {page_names}")
        return page_names
        
    except Exception as e:
        print(f"Error identifying wiki pages: {e}")
        return []

async def identify_mentioned_players(user_query: str, guild_members: list, requester_name: str = None) -> tuple[list, bool]:
    """
    Use Gemini to identify mentioned players in the query
    
    Returns:
        tuple: (list of mentioned players, bool indicating if query refers to all members)
    """
    if not config.gemini_api_key:
        print("Gemini API key not set")
        return [], False
    
    try:
        model = genai.GenerativeModel(config.gemini_model)
        
        # Format the guild members list for the prompt
        members_list = str(guild_members)
        
        prompt = f"""
        Clan member list:
        {members_list}

        Based on the above member list, analyze the user query and respond with ONE of these options:
        1. [ALL_MEMBERS] - if the query refers to all clan members or doesn't specify particular members
        2. [NO_MEMBERS] - if no clan members are mentioned or referenced
        3. A comma-separated list of UP TO 10 specific clan members mentioned or referenced

        Examples that should return [ALL_MEMBERS]:
        - "Who has the most Mole kills?"
        - "Who has the highest KBD KC?"
        - "Which clan member has the highest Firemaking level?"
        - "What's the highest total level in the clan?"
        - "Show me everyone's Zulrah KC"
        - "Compare all members' Slayer levels"
        - "Who is the best PvMer in the clan?"
        
        Examples that should return [NO_MEMBERS]:
        - "What's the best gear for Zulrah?"
        - "How do I complete Dragon Slayer 2?"
        - "What are the drop rates for Vorkath?"
        - "When was Chambers of Xeric released?"
        - "Tell me about the Inferno"
        - "What's the fastest way to train Runecrafting?"
        - "How much does an Abyssal whip cost?"
        - "Whats the price of an abyssal whip?"
        
        Examples that should return specific members:
        - "Compare Bob and Alice's stats"
        - "What's higher, John's or Mike's total level?"
        - "How many Vorkath kills does DragonSlayer have?"
        - "Show me my KC compared to Steve" (includes requester name)
        - "List tob KCs for me, Soup, Tovo, and Phug"

        If the user asks something about themself (ex: I/me etc, but not 'yourself' as that refers to the bot) then include the Requester name in the list.
        For multiple specific members, prioritize the most relevant ones to stay within the 10 member limit.

        Requester name: {requester_name or 'Unknown'}
        User query: {user_query}
        """
        
        generation = await asyncio.to_thread(
            lambda: model.generate_content(prompt)
        )
        response_text = generation.text.strip()
        
        # Check special responses
        if response_text == "[NO_MEMBERS]":
            print("No members identified in query")
            return [], False
        elif response_text == "[ALL_MEMBERS]":
            print("Query refers to all clan members")
            return [], True
            
        # Parse the comma-separated list of specific members
        mentioned_members = [name.strip() for name in response_text.split(',') if name.strip()][:10]
        print(f"Identified specific members (limited to 10): {mentioned_members}")
        return mentioned_members, False
        
    except Exception as e:
        print(f"Error identifying mentioned members: {e}")
        return [], False

async def generate_search_term(query):
    """Use Gemini to generate a search term based on the user query or determine if no search is needed"""
    if not config.gemini_api_key:
        print("Gemini API key not set")
        return query
    
    try:
        model = genai.GenerativeModel(config.gemini_model)
        
        # Get the current local date
        current_date = datetime.datetime.now().strftime("%B %d, %Y")
        
        prompt = f"""
        You are an assistant that helps generate effective search terms for Old School RuneScape (OSRS) related queries.
        
        Today's date is {current_date}.
        
        Given the following user query, determine if additional information is needed to provide a complete answer.
        
        If the query can be answered without additional information (e.g. simple or common knowledge, asked about yourself), respond with EXACTLY: [NO_SEARCH_NEEDED]
        
        Otherwise, generate a concise search term that would be effective for finding relevant information online.
        The search term should be focused on OSRS content and be 2-5 words long.
        
        User Query: {query}
        
        Respond ONLY with either [NO_SEARCH_NEEDED] or the search term, no additional text or explanation.
        """
        
        generation = await asyncio.to_thread(
            lambda: model.generate_content(prompt)
        )
        search_term = generation.text.strip()
        print(f"Generated search term: {search_term}")
        return search_term
        
    except Exception as e:
        print(f"Error generating search term: {e}")
        return query  # Fall back to original query if there's an error

async def is_player_only_query(user_query: str, player_data_list: list) -> bool:
    """
    Determine if a query can be answered using only player data without wiki/web searches
    
    Args:
        user_query: The user's query text
        player_data_list: List of player data objects
        
    Returns:
        Boolean indicating if the query can be answered with player data only
    """
    if not player_data_list or len(player_data_list) == 0:
        return False
        
    try:
        # If we have player data, use Gemini to determine if it's a player-only query
        model = genai.GenerativeModel(config.gemini_model)
        
        # Create a simplified version of the player data for analysis
        simplified_data = []
        for player_data in player_data_list:
            player_name = player_data.get('displayName', 'Unknown')
            simplified_data.append({
                'name': player_name,
                'data_available': 'skills and boss kill counts'
            })
            
        prompt = f"""
        Analyze this query about OSRS players and determine if it can be answered using ONLY player stats and boss kill counts, without needing any wiki information or web searches.
        
        Query: "{user_query}"
        
        Available player data: {simplified_data}
        
        Examples of player-only queries:
        - "Who has the highest Slayer level?"
        - "What's CyanideByte's highest boss KC?"
        - "Compare the Zulrah kill counts of these players"
        - "Who has more ToB KC?"
        - "Which player has the highest total level?"
        - "Who is better at PvM based on boss KCs?"
        
        Examples of queries that need wiki/web information:
        - "What's the best gear for Zulrah?"
        - "How do I complete Dragon Slayer 2?"
        - "What are the drop rates for Vorkath?"
        - "When was Chambers of Xeric released?"
        
        Respond with ONLY "YES" if the query can be answered with player data alone, or "NO" if wiki/web information is needed.
        """
        
        # Use a shorter timeout for this decision to avoid adding too much latency
        response = await asyncio.to_thread(
            lambda: model.generate_content(prompt).text.strip()
        )
        
        is_player_only = response.upper() == "YES"
        print(f"Query analysis result: {response} (is_player_only={is_player_only})")
        return is_player_only
        
    except Exception as e:
        print(f"Error determining if player-only query: {e}")
        # If there's an error, default to False (safer to get more information)
        return False

async def is_prohibited_query(user_query: str) -> bool:
    """
    Determine if a query is about prohibited topics that should not be answered.
    
    Args:
        user_query: The user's query text
        
    Returns:
        Boolean indicating if the query is about prohibited topics
        
    """
    if not config.gemini_api_key:
        print("Gemini API key not set")
        return False
        
    try:
        model = genai.GenerativeModel(config.gemini_model)
        
        prompt = f"""
        Analyze this query about OSRS and determine if it's about prohibited topics that should not be answered.

        Prohibited topics include:
        - Real world trading (buying/selling gold, accounts, or services)
        - Botting and bot clients
        - Unofficial 3rd party clients (like OSBuddy)
        - Private servers (RSPS)

        Query: "{user_query}"

        Examples of prohibited queries:
        - "Where can I buy OSRS gold?"
        - "What's the best botting client?"
        - "How do I set up OSBuddy?"
        - "Which gold selling sites are trustworthy?"
        - "What's the safest bot to use?"
        - "How much does power leveling service cost?"
        - "Can someone sell me an account?"
        - "What RSPS has the most players?"
        - "Which private server has the best PvP?"
        - "How do I join SpawnPK RSPS?"
        - "What's the IP for RoatPkz?"
        - "Best private server for ironman mode?"
        
        Respond with ONLY "YES" if the query is about prohibited topics, or "NO" if it's allowed.
        """
        
        # Use a shorter timeout for this decision
        response = await asyncio.to_thread(
            lambda: model.generate_content(prompt).text.strip()
        )
        
        is_prohibited = response.upper() == "YES"
        print(f"Query prohibition check result: {response} (is_prohibited={is_prohibited})")
        return is_prohibited
        
    except Exception as e:
        print(f"Error determining if prohibited query: {e}")
        # If there's an error, default to False (safer to allow query through)
        return False


async def identify_and_fetch_players(user_query: str, requester_name=None):
    """
    Identify mentioned players in the query and fetch their data
    
    Returns:
        tuple: (player_data_list, player_sources, is_all_members)
    """
    player_data_list = []
    player_sources = []
    
    try:
        # Get guild members first since we need both names and full data
        guild_members = get_guild_members()
        # Extract names from guild members
        guild_member_names = [member['player']['displayName'] for member in guild_members]
        identified_players, is_all_members = await identify_mentioned_players(user_query, guild_member_names, requester_name)

        if is_all_members:
            return [], [], True

        if identified_players:
            # Create a single session for all requests
            async with aiohttp.ClientSession() as session:
                # Create tasks for all player fetches
                # Find matching member data from guild members where displayName matches
                tasks = [fetch_player_details(next(member['player'] for member in guild_members if member['player']['displayName'] == player_name), session) for player_name in identified_players]
                
                # Execute all fetches concurrently
                print(f"Fetching data for {len(identified_players)} players concurrently...")
                player_data_results = await asyncio.gather(*tasks)
                
                # Process results
                for player_name, player_data in zip(identified_players, player_data_results):
                    if player_data:
                        player_data_list.append(player_data)
                        
                        # Add to sources
                        player_url = f"https://wiseoldman.net/players/{player_name.lower().replace(' ', '_')}"
                        player_sources.append({
                            'type': 'wiseoldman',
                            'name': player_name,
                            'url': player_url
                        })
                
                print(f"Successfully fetched data for {len(player_data_list)} out of {len(identified_players)} players")
                
        return player_data_list, player_sources, False
    except Exception as e:
        print(f"Error identifying and fetching players: {e}")
        return [], [], False

async def identify_and_fetch_wiki_pages(user_query: str, image_urls=None, status_message=None):
    """Identify and fetch wiki pages and web search results"""
    wiki_content = ""
    updated_page_names = []
    wiki_sources = []
    web_sources = []
    
    try:
        # Import here to avoid circular imports
        from osrs.search import get_web_search_context, format_search_results
        from osrs.wiki import fetch_osrs_wiki_pages
        
        # First identify and fetch wiki content
        page_names = await identify_wiki_pages(user_query, image_urls)
        if page_names:
            # Normalize page names
            normalized_wiki_page_names = [name.replace(' ', '_') for name in page_names]
            unique_normalized_names = sorted(list(set(normalized_wiki_page_names)))
            
            print(f"Fetching wiki pages: {', '.join(unique_normalized_names)}")
            wiki_content, redirects, rejected_pages = await fetch_osrs_wiki_pages(unique_normalized_names)
            
            # Process redirects and build wiki sources
            for page in unique_normalized_names:
                normalized_page_lookup = page.replace(' ', '_')
                redirected_page = redirects.get(normalized_page_lookup, normalized_page_lookup)
                final_page_name = redirected_page.replace(' ', '_')
                
                if final_page_name not in rejected_pages:
                    updated_page_names.append(final_page_name)
                    wiki_url = f"https://oldschool.runescape.wiki/w/{final_page_name}"
                    wiki_sources.append({
                        'type': 'wiki',
                        'name': final_page_name,
                        'url': wiki_url
                    })
        
        # Check if wiki content is sufficient before doing any web searches
        if wiki_content:
            is_wiki_sufficient = await is_wiki_only_query(user_query, wiki_content)
            if is_wiki_sufficient:
                print("Wiki content deemed sufficient, skipping web search")
                return wiki_content, updated_page_names, wiki_sources, []
        
        # If we need web content, do the web search
        if status_message:
            await status_message.edit(content="Searching the web...")
            
        search_results = await get_web_search_context(user_query)
        
        # Process search results
        for result in search_results:
            url = result.get('url', '')
            
            # Check for additional wiki pages we didn't find initially
            if "oldschool.runescape.wiki/w/" in url:
                page_name = url.split("/w/")[-1].replace(' ', '_')
                if not any(existing.lower() == page_name.lower() for existing in updated_page_names):
                    # Fetch this additional wiki page
                    print(f"Found additional wiki page: {page_name}")
                    additional_content, add_redirects, add_rejected = await fetch_osrs_wiki_pages([page_name])
                    
                    if additional_content and page_name not in add_rejected:
                        wiki_content += "\n" + additional_content
                        redirected_page = add_redirects.get(page_name, page_name)
                        final_page_name = redirected_page.replace(' ', '_')
                        updated_page_names.append(final_page_name)
                        wiki_sources.append({
                            'type': 'wiki',
                            'name': final_page_name,
                            'url': f"https://oldschool.runescape.wiki/w/{final_page_name}"
                        })
            else:
                # Add non-wiki sources
                web_sources.append({
                    'type': 'web',
                    'title': result.get('title', 'Web Source'),
                    'url': url
                })
        
        # Add formatted web content if we have any
        if web_sources:
            web_content = format_search_results(search_results)
            if wiki_content:
                wiki_content += "\n\n" + web_content
            else:
                wiki_content = web_content
            
        return wiki_content, updated_page_names, wiki_sources, web_sources
        
    except Exception as e:
        print(f"Error identifying and fetching wiki pages: {e}")
        return "", [], [], []

async def identify_mentioned_metrics(user_query: str) -> list:
    """
    Use Gemini to identify mentioned metrics (skills, bosses, activities) in the query
    
    Args:
        user_query: The user's query text
        
    Returns:
        list: List of identified metrics that match our predefined list
    """
    if not config.gemini_api_key:
        print("Gemini API key not set")
        return []
        
    try:
        model = genai.GenerativeModel(config.gemini_model)
        
        # Format the metrics lists for the prompt
        skills_str = ", ".join(SKILL_METRICS)
        activities_str = ", ".join(ACTIVITY_METRICS)
        bosses_str = ", ".join(BOSS_METRICS)
        
        prompt = f"""
        You are an assistant that identifies Old School RuneScape (OSRS) metrics mentioned in user queries.
        
        Available metrics:
        
        Skills: {skills_str}
        
        Activities: {activities_str}
        
        Bosses: {bosses_str}
        
        Analyze the following user query and identify any metrics (skills, bosses, activities) that are explicitly mentioned or clearly implied.
        
        User query: "{user_query}"
        
        Rules:
        1. Only include metrics that are explicitly mentioned or clearly implied in the query
        2. Return metrics in their exact format from the lists above (lowercase with underscores)
        3. If multiple metrics are mentioned, list them all
        4. If no metrics are mentioned, respond with "none"
        5. Common abbreviations should be mapped to their full metric name:
           - "cox" = "chambers_of_xeric"
           - "tob" = "theatre_of_blood"
           - "toa" = "tombs_of_amascut"
           - "cm" or "cox cm" = "chambers_of_xeric_challenge_mode"
           - "hm tob" or "hard tob" = "theatre_of_blood_hard_mode"
           - "expert toa" = "tombs_of_amascut_expert"
        
        Respond ONLY with a comma-separated list of identified metrics, or "none" if no metrics are mentioned.
        """
        
        generation = await asyncio.to_thread(
            lambda: model.generate_content(prompt)
        )
        response_text = generation.text.strip().lower()
        
        if response_text == "none":
            print("No metrics identified in query")
            return []
            
        # Parse the comma-separated list of metrics and explicitly normalize them
        mentioned_metrics = []
        for metric in response_text.split(','):
            if metric.strip():
                # Explicitly lowercase and replace spaces with underscores
                normalized_metric = metric.strip().lower().replace(' ', '_')
                mentioned_metrics.append(normalized_metric)
        
        # Filter to only include metrics that match our predefined list
        valid_metrics = [metric for metric in mentioned_metrics if metric in ALL_METRICS]
        
        print(f"Identified metrics: {valid_metrics}")
        return valid_metrics
        
    except Exception as e:
        print(f"Error identifying mentioned metrics: {e}")
        return []

async def identify_and_fetch_metrics(user_query: str):
    """
    Identify mentioned metrics in the query and fetch their data
    
    Args:
        user_query: The user's query text
        
    Returns:
        dict: Dictionary mapping metric names to their scoreboard data
    """
    metrics_data = {}
    
    try:
        # Identify metrics mentioned in the query
        identified_metrics = await identify_mentioned_metrics(user_query)
        
        if not identified_metrics:
            print("No metrics identified in query")
            return metrics_data
            
        print(f"Fetching data for {len(identified_metrics)} metrics...")
        
        # Fetch data for each identified metric
        for metric in identified_metrics:
            try:
                scoreboard = fetch_metric(metric)
                metrics_data[metric] = scoreboard
                print(f"Successfully fetched data for metric: {metric}")
            except Exception as e:
                print(f"Error fetching data for metric {metric}: {e}")
                
        print(f"Successfully fetched data for {len(metrics_data)} out of {len(identified_metrics)} metrics")
        return metrics_data
        
    except Exception as e:
        print(f"Error identifying and fetching metrics: {e}")
        return {}

async def is_wiki_only_query(user_query: str, wiki_content: str) -> bool:
    """
    Determine if the provided wiki content contains sufficient information to answer the query
    without needing additional web searches.
    
    Args:
        user_query: The user's query text
        wiki_content: The full wiki page content
        
    Returns:
        Boolean indicating if the query can be answered with the provided wiki content alone
    """
    if not wiki_content:
        return False
        
    try:
        model = genai.GenerativeModel(config.gemini_model)
            
        prompt = f"""
        Analyze if the provided OSRS wiki content has enough information to fully answer this query without needing additional web searches.
        
        Query: "{user_query}"
        
        Wiki content: "{wiki_content}"
        
        Your task is to determine if this wiki content alone contains sufficient information to provide a complete and accurate answer to the query.
        
        For queries about item stats, equipment stats, combat bonuses, or weapon attributes, check carefully if the content includes:
        - Combat stats sections with attack/defense bonuses
        - Equipment stats and requirements
        - Special attack details (if applicable)
        - Item attributes like speed, accuracy, or damage
        - Price information
        
        Even if only basic item stats are present but they directly answer what the user is asking about, consider this sufficient.
        Respond with ONLY "YES" if the wiki content has enough information, or "NO" if additional web searching would be needed to properly answer the query.
        """
        
        # Use a shorter timeout for this decision
        response = await asyncio.to_thread(
            lambda: model.generate_content(prompt).text.strip()
        )
        
        is_wiki_sufficient = response.upper() == "YES"
        print(f"Wiki content sufficiency analysis: {response} (is_wiki_sufficient={is_wiki_sufficient})")
        return is_wiki_sufficient
        
    except Exception as e:
        print(f"Error analyzing wiki content sufficiency: {e}")
        # If there's an error, default to False (safer to get more information)
        return False
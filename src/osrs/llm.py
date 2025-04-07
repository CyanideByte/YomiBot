import asyncio
import aiohttp
from PIL import Image
import io
import time
import datetime
import google.generativeai as genai
from config.config import config

# Import wiki-related functions from wiki.py
from osrs.wiki import fetch_osrs_wiki_pages, fetch_osrs_wiki
# Import web search functions from search.py
from osrs.search import get_web_search_context, format_search_results
# Import player tracking functions from tracker.py
from wiseoldman.tracker import get_guild_members, fetch_player_details, format_player_data
# Store user's recent interactions (user_id -> {timestamp, query, response, pages})
user_interactions = {}

# Time window in seconds for considering previous interactions (5 minutes)
INTERACTION_WINDOW = 60  # 1 minutes * 60 seconds

# Configure the Gemini API
if config.gemini_api_key:
    genai.configure(api_key=config.gemini_api_key)

# System prompt for Gemini
# Unified system prompt for both player data and wiki information
UNIFIED_SYSTEM_PROMPT = """
You are an Old School RuneScape (OSRS) expert assistant. Your task is to answer questions about OSRS using:
1. Player data from WiseOldMan when provided
2. OSRS Wiki information when available
3. Web search results when necessary

Content Rules:
1. Use only the provided information sources when possible
2. If player data is available, analyze it thoroughly to answer player-specific questions
3. If wiki/web information is available, use it to answer game mechanic questions
4. When appropriate, combine player data with wiki information for comprehensive answers
5. Prioritize key information the player needs
6. Format information clearly and consistently
7. Break information into clear sections
8. Keep answers concise (under 2000 characters)
9. ALWAYS include a "Sources:" section at the end of your response with all source URLs

Remember: Create clear, easy-to-read responses that focus on the key information.
"""

# Legacy system prompt removed - now using UNIFIED_SYSTEM_PROMPT

async def fetch_image(image_url: str) -> Image.Image:
    """Download and convert image from URL to PIL Image"""
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url) as response:
            if response.status != 200:
                raise Exception(f"Failed to download image: {response.status}")
            image_data = await response.read()
            return Image.open(io.BytesIO(image_data))

async def identify_items_in_images(images: list[Image.Image]) -> list[str]:
    """Use Gemini to identify OSRS items/NPCs/locations in images"""
    if not images:
        return []

    try:
        model = genai.GenerativeModel(config.gemini_model)
        prompt = """Name the OSRS items, NPCs, or locations you see in these images. Use exact wiki page names with underscores.

        Respond ONLY with comma-separated wiki page names, no explanations or other text.
        Example response format: "Dragon_scimitar,Abyssal_whip,Lumbridge_Castle"
        """
        
        content = [prompt] + images
        generation = await asyncio.to_thread(
            lambda: model.generate_content(content)
        )
        return [name.strip() for name in generation.text.split(',') if name.strip()]
    except Exception as e:
        print(f"Error identifying items in images: {e}")
        return []

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
            
        page_names = [name.strip() for name in response_text.split(',') if name.strip()][:5]
        print(f"Identified wiki pages: {page_names}")
        return page_names
        
    except Exception as e:
        print(f"Error identifying wiki pages: {e}")
        return []

async def identify_mentioned_players(user_query: str, guild_members: list, requester_name: str = None):
    """Use Gemini to identify mentioned players in the query"""
    if not config.gemini_api_key:
        print("Gemini API key not set")
        return []
    
    try:
        model = genai.GenerativeModel(config.gemini_model)
        
        # Format the guild members list for the prompt
        members_list = str(guild_members)
        
        prompt = f"""
        Clan member list:
        {members_list}

        Based on the above member list, respond with a comma separated list of clan members that you think the user is referring to in the following query or [NO_MEMBERS] if none are mentioned. If the user refers to themself (ex: I/me etc) then add the Requester name to the list as well. Do not respond with anything else.

        Requester name: {requester_name or 'Unknown'}
        User query: {user_query}
        """
        
        generation = await asyncio.to_thread(
            lambda: model.generate_content(prompt)
        )
        response_text = generation.text.strip()
        
        # Check if the response indicates no members were found
        if response_text == "[NO_MEMBERS]":
            print("No members identified in query")
            return []
            
        # Parse the comma-separated list of members
        mentioned_members = [name.strip() for name in response_text.split(',') if name.strip()]
        print(f"Identified mentioned members: {mentioned_members}")
        return mentioned_members
        
    except Exception as e:
        print(f"Error identifying mentioned members: {e}")
        return []

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
# In-memory cache with TTL
query_cache = {}

async def get_cached_or_fetch(cache_key, fetch_func, ttl_seconds=300):
    """Get data from cache or fetch it if not available or expired"""
    current_time = time.time()
    
    # Check if in cache and not expired
    if cache_key in query_cache:
        entry = query_cache[cache_key]
        if current_time - entry['timestamp'] < ttl_seconds:
            print(f"Cache hit for key: {cache_key}")
            return entry['data']
    
    # If not in cache or expired, fetch fresh data
    print(f"Cache miss for key: {cache_key}, fetching fresh data")
    data = await fetch_func()
    
    # Update cache
    query_cache[cache_key] = {
        'data': data,
        'timestamp': current_time
    }
    
    return data

# Removed unused functions that were replaced by process_unified_query

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
        model = genai.GenerativeModel('gemini-1.5-flash')
        
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

async def identify_and_fetch_players(user_query: str, mentioned_players=None, requester_name=None):
    """Identify mentioned players in the query and fetch their data"""
    player_data_list = []
    player_sources = []
    
    try:
        # If mentioned_players is already provided, use that
        if mentioned_players:
            for player_name in mentioned_players:
                player_data = fetch_player_details(player_name)
                if player_data:
                    player_data_list.append(player_data)
                    
                    # Add to sources
                    player_url = f"https://wiseoldman.net/players/{player_name.lower().replace(' ', '_')}"
                    player_sources.append({
                        'type': 'wiseoldman',
                        'name': player_name,
                        'url': player_url
                    })
            return player_data_list, player_sources
        
        # Otherwise, identify players from the query
        guild_members = get_guild_members()
        identified_players = await identify_mentioned_players(user_query, guild_members, requester_name)
        
        for player_name in identified_players:
            player_data = fetch_player_details(player_name)
            if player_data:
                player_data_list.append(player_data)
                
                # Add to sources
                player_url = f"https://wiseoldman.net/players/{player_name.lower().replace(' ', '_')}"
                player_sources.append({
                    'type': 'wiseoldman',
                    'name': player_name,
                    'url': player_url
                })
                
        return player_data_list, player_sources
    except Exception as e:
        print(f"Error identifying and fetching players: {e}")
        return [], []

async def identify_and_fetch_wiki_pages(user_query: str, image_urls=None):
    """Identify and fetch wiki pages and web search results"""
    wiki_content = ""
    wiki_sources = []
    web_sources = []
    
    try:
        # Identify relevant wiki pages, potentially using image analysis
        page_names = await identify_wiki_pages(user_query, image_urls)
        
        # Set up variables for content and page tracking
        updated_page_names = []
        wiki_page_names = page_names.copy()  # Make a copy to avoid modifying the original
        non_wiki_sources = []
        
        # If we have less than 5 wiki pages identified or none at all, perform web search
        if len(wiki_page_names) < 5:
            print(f"Found {len(wiki_page_names)} wiki pages, performing web search to find more sources...")
            
            # Get raw search results
            search_results = await get_web_search_context(user_query)
            
            # Process each search result
            for result in search_results:
                url = result.get('url', '')
                
                # Check if it's an OSRS wiki page
                if "oldschool.runescape.wiki/w/" in url:
                    # Extract the page name from the URL
                    page_name = url.split("/w/")[-1]
                    
                    # Check if this page is already in our list to avoid duplicates
                    if page_name not in wiki_page_names:
                        wiki_page_names.append(page_name)
                        print(f"Added wiki page from search results: {page_name}")
                        
                        # If we have 5 wiki pages, stop adding more
                        if len(wiki_page_names) >= 5:
                            break
                else:
                    # This is not a wiki page, add to non-wiki sources
                    non_wiki_sources.append(result)
        
        # Now fetch all wiki pages we've identified
        if wiki_page_names:
            print(f"Fetching wiki pages: {', '.join(wiki_page_names)}")
            
            # Fetch content from identified wiki pages
            wiki_content, redirects = await asyncio.to_thread(
                fetch_osrs_wiki_pages, wiki_page_names
            )
            
            # Update page_names with redirected names for correct source URLs
            for page in wiki_page_names:
                redirected_page = redirects.get(page, page)
                updated_page_names.append(redirected_page)
                
                # Add to sources
                wiki_url = f"https://oldschool.runescape.wiki/w/{redirected_page.replace(' ', '_')}"
                wiki_sources.append({
                    'type': 'wiki',
                    'name': redirected_page,
                    'url': wiki_url
                })
            
            print(f"Retrieved content from {len(wiki_page_names)} wiki pages")
            if redirects:
                print(f"Followed redirects: {redirects}")
        
        # If we have non-wiki sources, format them and append to wiki_content
        if non_wiki_sources:
            print(f"Adding {len(non_wiki_sources)} non-wiki sources to context")
            non_wiki_content = format_search_results(non_wiki_sources)
            wiki_content += non_wiki_content
            
            # Add to sources
            for result in non_wiki_sources:
                if 'url' in result:
                    web_sources.append({
                        'type': 'web',
                        'title': result.get('title', 'Web Source'),
                        'url': result['url']
                    })
        
        # If we have no content at all, perform a full web search
        if not wiki_content:
            print("No wiki pages identified, performing full web search...")
            
            # Get raw search results
            search_results = await get_web_search_context(user_query)
            
            # Format the results for use as context
            wiki_content = format_search_results(search_results)
            print("Using web search results as context")
            
            # Add to sources
            for result in search_results:
                if 'url' in result:
                    web_sources.append({
                        'type': 'web',
                        'title': result.get('title', 'Web Source'),
                        'url': result['url']
                    })
        
        return wiki_content, updated_page_names, wiki_sources, web_sources
    except Exception as e:
        print(f"Error identifying and fetching wiki pages: {e}")
        return "", [], [], []

def collect_source_urls(player_sources, wiki_sources, web_sources):
    """Collect all source URLs into a single list"""
    all_sources = []
    
    # Add player sources
    for source in player_sources:
        all_sources.append(source['url'])
    
    # Add wiki sources
    for source in wiki_sources:
        all_sources.append(source['url'])
    
    # Add web sources
    for source in web_sources:
        all_sources.append(source['url'])
    
    return all_sources

def build_sources_section(player_sources, wiki_sources, web_sources):
    """Build a sources section for the response"""
    sources = collect_source_urls(player_sources, wiki_sources, web_sources)
    
    if not sources:
        return ""
        
    sources_section = "\n\nSources:"
    for url in sources:
        # Ensure consistent formatting without prefixes like "Player data:"
        clean_url = url.split("://")[-1] if "://" in url else url
        sources_section += f"\n- <https://{clean_url}>"
        
    return sources_section

# Simplified ensure_all_sources_included function
def ensure_all_sources_included(response, player_sources, wiki_sources, web_sources):
    """Ensure all sources are included in the response using a robust method."""
    import re

    # 1. Collect all expected source URLs
    all_sources = collect_source_urls(player_sources, wiki_sources, web_sources)
    unique_sources = sorted(list(set(all_sources))) # Ensure uniqueness and consistent order

    # 2. If no sources expected, return the response as is
    if not unique_sources:
        return response

    # 3. Define patterns
    url_pattern = re.compile(r'<(https?://[^\s<>"]+)>')
    # Pattern to find "Sources:" or "Source:" header, case-insensitive, possibly preceded by newlines/whitespace
    sources_header_pattern = re.compile(r'^([ \t]*\n)?(Sources?):', re.MULTILINE | re.IGNORECASE)

    # 4. Try to find an existing "Sources:" section
    header_match = sources_header_pattern.search(response)
    existing_section_valid_and_complete = False

    if header_match:
        sources_start_index = header_match.start()
        # Extract text from the header onwards
        sources_section_text = response[sources_start_index:]
        # Find all URLs within this potential section
        existing_urls = sorted(list(set(url_pattern.findall(sources_section_text))))

        # Check if the existing section contains exactly the set of expected unique URLs
        if set(existing_urls) == set(unique_sources):
            existing_section_valid_and_complete = True
            print("Existing Sources section is valid and complete.")
        else:
            print(f"Existing Sources section found but is incomplete or incorrect. Expected: {unique_sources}, Found: {existing_urls}")
    else:
        print("No existing Sources section found.")
        # Check if URLs exist *without* a header, indicating a malformed response from LLM
        urls_without_header = url_pattern.findall(response)
        if urls_without_header:
            print("Found URLs without a Sources header, indicating LLM ignored instructions.")


    # 5. If section is valid and complete, return (potentially after minor cleanup)
    if existing_section_valid_and_complete:
        # Minor cleanup: remove extra newlines within the section
        sources_start_index = header_match.start()
        pre_sources = response[:sources_start_index]
        sources_part = response[sources_start_index:]
        # Replace multiple consecutive newlines before a source item with a single newline
        sources_part = re.sub(r'\n\s*\n(- <https?://)', r'\n\1', sources_part)
        # Ensure the header itself is preceded by exactly two newlines
        pre_sources = pre_sources.rstrip() + "\n\n"
        # Ensure the header line itself is just "Sources:"
        sources_part = re.sub(r'^(Sources?):', 'Sources:', sources_part.strip(), count=1, flags=re.IGNORECASE)

        return pre_sources + sources_part

    # 6. Otherwise (section missing, incomplete, or malformed), rebuild the sources section
    print("Rebuilding Sources section.")
    response_base = response # Start with the original response

    # If a header existed, strip everything from the header onwards
    if header_match:
        response_base = response[:header_match.start()].rstrip()
    else:
        # If no header, try to remove trailing lines that look like source URLs
        lines = response.rstrip().split('\n')
        last_non_url_line_index = -1
        # Find the index of the last line that does *not* look like a source URL line
        for i in range(len(lines) - 1, -1, -1):
             # A line is likely a source URL if it starts with '- <http' or just '<http' after stripping whitespace
            line_content = lines[i].strip()
            if not (line_content.startswith('- <http') or line_content.startswith('<http')):
                last_non_url_line_index = i
                break

        # If we found loose URLs at the end (i.e., the last line was a URL line)
        if last_non_url_line_index < len(lines) - 1:
            print(f"Stripping trailing URL-like lines from index {last_non_url_line_index + 1}")
            # Take lines up to and including the last non-URL line
            response_base = '\n'.join(lines[:last_non_url_line_index + 1]).rstrip()
        else:
            # No trailing URL lines found, keep the response as is
             response_base = response.rstrip()


    # Build the new section string
    new_sources_section = "\n\nSources:"
    for url in unique_sources:
        new_sources_section += f"\n- <{url}>"

    # Combine base response with the new section
    final_response = response_base + new_sources_section

    return final_response

async def process_unified_query(
    user_query: str,
    user_id: str = None,
    image_urls: list[str] = None,
    mentioned_players: list[str] = None,
    requester_name: str = None
) -> str:
    """
    Unified function to process queries using both player data and wiki/web information
    
    Args:
        user_query: The user's query text
        user_id: Optional user ID for tracking interactions
        image_urls: Optional list of image URLs to analyze
        mentioned_players: Optional list of already identified player names
        requester_name: Optional name of the user making the request
        
    Returns:
        Formatted response text
    """
    if not config.gemini_api_key:
        return "Sorry, the OSRS assistant is not available because the Gemini API key is not set."
    
    try:
        # Start performance tracking
        start_time = time.time()
        
        # First, identify and fetch player data
        player_task = identify_and_fetch_players(user_query, mentioned_players, requester_name)
        player_data_list, player_sources = await player_task
        
        # Determine if this is a player-only query
        is_player_only = False
        if player_data_list:
            is_player_only = await is_player_only_query(user_query, player_data_list)
            print(f"Query determined to be player-only: {is_player_only}")
        
        # Only fetch wiki/web content if this is not a player-only query
        if not is_player_only:
            print("Fetching wiki and web content...")
            wiki_task = identify_and_fetch_wiki_pages(user_query, image_urls)
            wiki_content, updated_page_names, wiki_sources, web_sources = await wiki_task
        else:
            print("Skipping wiki and web searches for player-only query")
            wiki_content = ""
            updated_page_names = []
            wiki_sources = []
            web_sources = []
        
        # Log performance for data fetching
        data_fetch_time = time.time() - start_time
        print(f"Data fetching completed in {data_fetch_time:.2f} seconds")
        
        # Format player data for context if available
        player_context = ""
        if player_data_list:
            for player_data in player_data_list:
                player_name = player_data.get('displayName', 'Unknown player')
                player_context += f"\n===== {player_name} DATA =====\n"
                player_context += format_player_data(player_data)
                player_context += "\n\n"
            print(f"Formatted data for {len(player_data_list)} players")
        
        # Use text-based approach for response formatting
        model = genai.GenerativeModel(config.gemini_model)
        
        # Construct the prompt based on available data
        if is_player_only:
            # For player-only queries, use a more focused prompt
            prompt = f"""
            You are an Old School RuneScape (OSRS) expert assistant. Your task is to answer questions about OSRS players using the provided player data.
            
            User Query: {user_query}
            
            Player Data:
            {player_context}
            
            This query can be answered using ONLY the player data provided. Do not speculate about information not present in the player data.
            """
        else:
            # For queries that need both data sources, use the unified prompt
            prompt = f"""
            {UNIFIED_SYSTEM_PROMPT}
            
            User Query: {user_query}
            """
            
            # Add player data if available
            if player_context:
                prompt += f"""
                
                Player Data:
                {player_context}
                """
            
            # Add wiki/web content if available
            if wiki_content:
                prompt += f"""
                
                OSRS Wiki and Web Information:
                {wiki_content}
                """
        
        # Add formatting instructions
        prompt += """
        
        Provide a response following these specific formatting rules:
        1. Start with a **Section Header**
        2. Use - for list items (not bullet points)
        3. Bold ONLY:
           - Player names (e.g., **PlayerName**)
           - Item names (e.g., **Abyssal whip**)
           - Monster/boss names (e.g., **Abyssal demon**)
           - Location names (e.g., **Wilderness**)
           - Section headers
        4. Do NOT bold:
           - Drop rates
           - Prices
           - Combat stats
           - Other numerical values
        5. ALWAYS include sources at the end of your response:
           - You MUST start a new paragraph with the exact text "Sources:" (including the colon)
           - The "Sources:" header MUST be on its own line
           - List each source URL on its own line with a hyphen (-) bullet point
           - Format ALL sources consistently as: "- <URL>" (no prefixes like "Player data:")
           - Example:
             
             Sources:
             - <https://oldschool.runescape.wiki/w/Abyssal_whip>
             - <https://wiseoldman.net/players/playername>
           
           - Do NOT add empty lines between sources
           - Do NOT include duplicate URLs in the sources section
           - Include ALL relevant sources, including player data sources
           - The "Sources:" header is ABSOLUTELY REQUIRED for ALL responses
           - NEVER list URLs without the "Sources:" header
        """
        
        # Generate the response
        response_start_time = time.time()
        response = await asyncio.to_thread(
            lambda: model.generate_content(prompt).text
        )
        response_time = time.time() - response_start_time
        print(f"Generated response in {response_time:.2f} seconds")
        
        # Ensure all sources are included
        response = ensure_all_sources_included(response, player_sources, wiki_sources, web_sources)
        
        # Clean and format URLs consistently
        # Reuse the existing URL cleaning logic from process_user_query
        import re
        
        # Define a comprehensive cleaning function for URL patterns
        def clean_url_patterns(text, url, escaped_url=None):
            if escaped_url is None:
                escaped_url = url
            
            # Handle the specific broken format with both escaped and unescaped versions
            # ([URL](<URL>))
            text = re.sub(r'\(\[\s*' + re.escape(escaped_url) + r'\s*\]\s*\(\s*<\s*' + re.escape(url) + r'\s*>\s*\)\s*\)', f"(<{url}>)", text)
            
            # Handle other common patterns
            patterns = [
                (f"[{escaped_url}]({url})", f"<{url}>"),  # Markdown with escaped URL
                (f"[{url}]({url})", f"<{url}>"),  # Markdown style
                (f"[<{url}>]", f"<{url}>"),  # Bracketed angle brackets
                (f"(<{url}>)", f"<{url}>"),  # Parenthesized angle brackets - preserve this format
                (f"[{url}]", f"<{url}>"),  # Simple brackets
                (f"({url})", f"<{url}>"),  # Simple parentheses
            ]
            
            # Apply each pattern replacement
            for pattern, replacement in patterns:
                text = text.replace(pattern, replacement)
            
            # Ensure the URL is wrapped in angle brackets if it's not already
            # But avoid double-wrapping URLs that are already properly formatted
            if f"<{url}>" not in text and url in text:
                # Use regex with word boundaries to avoid partial replacements
                text = re.sub(r'(?<!\<)' + re.escape(url) + r'(?!\>)', f"<{url}>", text)
            
            return text
        
        # Clean wiki URLs
        for source in wiki_sources:
            url = source['url']
            clean_page = source['name'].replace(' ', '_')
            
            # Handle escaped underscores
            escaped_page = clean_page.replace('_', '\\_')
            escaped_url = f"https://oldschool.runescape.wiki/w/{escaped_page}"
            
            # Apply the cleaning function with both regular and escaped URLs
            response = clean_url_patterns(response, url, escaped_url)
        
        # Clean player URLs
        for source in player_sources:
            url = source['url']
            response = clean_url_patterns(response, url)
        
        # Clean web URLs
        for source in web_sources:
            url = source['url']
            response = clean_url_patterns(response, url)
        
        # Now find and clean all other URLs in the response
        # More aggressive URL detection and wrapping
        unwrapped_url_pattern = re.compile(r'(?<!\<)(https?://[^\s<>"]+)(?!\>)')
        response = unwrapped_url_pattern.sub(r'<\1>', response)
        
        # Store this interaction if user_id is provided
        if user_id:
            user_interactions[user_id] = {
                'timestamp': time.time(),
                'query': user_query,
                'response': response,
                'pages': updated_page_names
            }
            print(f"Stored interaction for user {user_id}")
        
        # Log total processing time
        total_time = time.time() - start_time
        print(f"Total processing time: {total_time:.2f} seconds")
        
        # Truncate if too long for Discord
        return response[:1900] + "\n\n(Response length exceeded)" if len(response) > 1900 else response
        
    except Exception as e:
        print(f"Error processing unified query: {e}")
        return f"Error processing your query: {str(e)}"

async def roast_player(player_data):
    """
    Generate a humorous roast for a player based on their stats
    """
    if not config.gemini_api_key:
        return "Sorry, the player roast feature is not available because the Gemini API key is not set."
    
    try:
        model = genai.GenerativeModel(config.gemini_model)
        
        # Format player data for context
        player_context = format_player_data(player_data)
        player_name = player_data.get('displayName', 'Unknown player')
        
        prompt = f"""
        You are a witty Old School RuneScape roast generator. Your task is to create a humorous, slightly sarcastic roast of a player based on their stats.
        
        Rules for the roast:
        1. Focus ONLY on the player's low skills, low boss kill counts, or high counts in easy/noob bosses or skills
        2. The roast should be ONE concise paragraph (not bullet points)
        3. Be witty and humorous, but not overly mean
        4. Mention specific skills or bosses from their data that are notably low or "noob-like"
        5. If they have high kill counts in easy bosses but low counts in hard bosses, definitely mention that
        6. If they have high levels in easy skills but low levels in challenging skills, point that out
        7. Keep the tone light and playful
        
        Player Name: {player_name}
        
        Player Stats:
        {player_context}
        
        Generate a single paragraph roast focusing on the player's noob-like stats or achievements.
        """
        
        response = await asyncio.to_thread(
            lambda: model.generate_content(prompt).text
        )
        
        # Format the response for Discord
        formatted_response = f"**Roast of {player_name}**\n\n{response}"
        
        return formatted_response
        
    except Exception as e:
        print(f"Error generating player roast: {e}")
        return f"Error generating roast: {str(e)}"

# Discord command registration - depends on wiki functionality
def register_commands(bot):
    @bot.command(name='askyomi', aliases=['yomi', 'ask'])
    async def askyomi(ctx, *, user_query: str = ""):
        # Get the user's Discord ID for context tracking
        user_id = str(ctx.author.id)
        
        # Check for image attachments
        image_urls = []
        if ctx.message.attachments:
            for attachment in ctx.message.attachments:
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    image_urls.append(attachment.url)

        # If no query text and no images, show error
        if not user_query and not image_urls:
            await ctx.send("Please provide a question or attach an image to analyze.")
            return

        # Let the user know we're processing their request and store the message object
        # Use reference parameter to make it a reply to the user's message
        if image_urls:
            processing_msg = await ctx.send(
                "Processing your image(s) and request, this may take a moment...",
                reference=ctx.message
            )
        else:
            processing_msg = await ctx.send(
                "Processing your request, this may take a moment...",
                reference=ctx.message
            )

        try:
            # Get guild members to check if any are mentioned in the query
            guild_members = get_guild_members()
            
            # Use Gemini to identify mentioned players in the query
            mentioned_members = await identify_mentioned_players(
                user_query,
                guild_members,
                ctx.author.display_name  # Pass the requester's name
            )
            
            # Use the unified query processor
            response = await process_unified_query(
                user_query or "What is this OSRS item?",
                user_id=user_id,
                image_urls=image_urls,
                mentioned_players=mentioned_members,
                requester_name=ctx.author.display_name
            )
            
            await processing_msg.edit(content=response)
        except Exception as e:
            # If there was an error, edit the processing message with the error
            await processing_msg.edit(content=f"Error processing your request: {str(e)}")
            
    @bot.command(name='roast', help='Roasts a player based on their OSRS stats.')
    async def roast(ctx, *, username=None):
        """Command to roast a player based on their OSRS stats."""
        if username is None:
            await ctx.send("Please provide a username to roast. Example: !roast zezima")
            return
        
        # Let the user know we're processing their request
        processing_msg = await ctx.send(
            f"Preparing a roast for {username}, this may take a moment...",
            reference=ctx.message
        )
        
        try:
            # Fetch player details
            player_data = fetch_player_details(username)
            
            if player_data:
                # Generate the roast
                roast_response = await roast_player(player_data)
                await processing_msg.edit(content=roast_response)
            else:
                await processing_msg.edit(content=f"Could not find player '{username}' or an error occurred.")
        except Exception as e:
            await processing_msg.edit(content=f"Error roasting player: {str(e)}")
import asyncio
import datetime
import aiohttp
import google.generativeai as genai
from config.config import config
from osrs.llm.image_processing import fetch_image, identify_items_in_images
from osrs.wiseoldman import get_guild_member_names, fetch_player_details

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

        Based on the above member list, respond with a comma separated list of clan members that you think the user is referring to in the following query or [NO_MEMBERS] if none are mentioned. If the user refers to themself (ex: I/me etc, but not 'yourself' as that refers to the bot) then add the Requester name to the list as well. Do not respond with anything else.

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

async def identify_and_fetch_players(user_query: str, requester_name=None):
    """Identify mentioned players in the query and fetch their data"""
    player_data_list = []
    player_sources = []
    
    try:
        # Identify players from the query
        guild_members = get_guild_member_names()
        identified_players = await identify_mentioned_players(user_query, guild_members, requester_name)

        if identified_players:
            # Create a single session for all requests
            async with aiohttp.ClientSession() as session:
                # Create tasks for all player fetches
                tasks = [fetch_player_details(player_name, session) for player_name in identified_players]
                
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
                
        return player_data_list, player_sources
    except Exception as e:
        print(f"Error identifying and fetching players: {e}")
        return [], []

async def identify_and_fetch_wiki_pages(user_query: str, image_urls=None, status_message=None):
    """Identify and fetch wiki pages and web search results"""
    wiki_content = ""
    wiki_sources = []
    web_sources = []
    search_results = None  # Initialize search_results variable to store the first call result
    
    try:
        # Import here to avoid circular imports
        from osrs.search import get_web_search_context, format_search_results
        from osrs.wiki import fetch_osrs_wiki_pages
        
        # Identify relevant wiki pages, potentially using image analysis
        page_names = await identify_wiki_pages(user_query, image_urls)
        
        # Set up variables for content and page tracking
        updated_page_names = []
        wiki_page_names = page_names.copy()  # Make a copy to avoid modifying the original
        non_wiki_sources = []
        
        # If we have less than 5 wiki pages identified or none at all, perform web search
        if len(wiki_page_names) < 5:
            print(f"Found {len(wiki_page_names)} wiki pages, performing web search...")
            
            # Get search results directly
            if status_message:
                await status_message.edit(content="Performing web search...")
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
            wiki_content, redirects = await fetch_osrs_wiki_pages(wiki_page_names)
            
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
            
            # Reuse search results if we already have them
            if search_results is None:
                if status_message:
                    await status_message.edit(content="Performing web search...")
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
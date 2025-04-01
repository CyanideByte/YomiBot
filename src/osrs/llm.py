import asyncio
import aiohttp
from PIL import Image
import io
import time
import google.generativeai as genai
from config.config import config

# Import wiki-related functions from wiki.py
from osrs.wiki import fetch_osrs_wiki_pages
# Import web search functions from search.py
from osrs.search import get_web_search_context
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
SYSTEM_PROMPT = """
You are an Old School RuneScape (OSRS) expert assistant. Your task is to answer questions about OSRS using information provided from the OSRS Wiki.

Content Rules:
1. Use only the provided wiki information when possible.
2. If you cannot provide an answer with the information given, state that clearly, and then provide an answer based on your own knowledge.
3. Prioritize key information the player needs
4. Format information clearly and consistently
5. Break information into clear sections
6. Keep answers concise (under 2000 characters)

Remember: Create clear, easy-to-read responses that focus on the key information.
"""

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
        model = genai.GenerativeModel(config.gemini_flash_model)
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
        model = genai.GenerativeModel(config.gemini_flash_model)
        
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

async def generate_search_term(query):
    """Use Gemini to generate a search term based on the user query"""
    if not config.gemini_api_key:
        print("Gemini API key not set")
        return query
    
    try:
        model = genai.GenerativeModel(config.gemini_flash_model)
        
        prompt = f"""
        You are an assistant that helps generate effective search terms for Old School RuneScape (OSRS) related queries.
        
        Given the following user query, generate a concise search term that would be effective for finding relevant information online.
        The search term should be focused on OSRS content and be 2-5 words long.
        
        User Query: {query}
        
        Respond ONLY with the search term, no additional text or explanation.
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

async def process_player_data_query(user_query: str, player_data_list: list, image_urls: list[str] = None) -> str:
    """Process a user query with player data using Gemini"""
    if not config.gemini_api_key:
        return "Sorry, the OSRS player query assistant is not available because the Gemini API key is not set."
    
    try:
        model = genai.GenerativeModel(config.gemini_flash_model)
        
        # Format player data for context
        player_context = ""
        for player_data in player_data_list:
            player_name = player_data.get('displayName', 'Unknown player')
            player_context += f"\n===== {player_name} DATA =====\n"
            player_context += format_player_data(player_data)
            player_context += "\n\n"
        
        prompt = f"""
        You are an Old School RuneScape (OSRS) expert assistant. Your task is to answer questions about OSRS players using the provided player data.
        
        Formatting Rules:
        1. Use * for bullet points (they format correctly in Discord)
        2. Bold important information with **text**, such as:
           * Player names (e.g., **PlayerName**)
           * Boss or skill names
        3. Keep answers concise (under 2000 characters)
        4. Break information into clear sections if needed
        
        User Query: {user_query}
        
        Player Data:
        {player_context}
        
        Provide a helpful response based on the player data and the user's query.
        """
        
        response = await asyncio.to_thread(
            lambda: model.generate_content(prompt).text
        )
        
        return response
        
    except Exception as e:
        print(f"Error processing player data query: {e}")
        return f"Error processing your player data query: {str(e)}"

async def process_user_query(user_query: str, image_urls: list[str] = None, user_id: str = None) -> str:
    """Process a user query about OSRS using Gemini and the OSRS Wiki, optionally with images"""
    if not config.gemini_api_key:
        return "Sorry, the OSRS Wiki assistant is not available because the Gemini API key is not set."
        
    try:
        # Identify relevant wiki pages, potentially using image analysis
        page_names = await identify_wiki_pages(user_query, image_urls)
        
        # Check if we have no pages and should use previous context
        previous_context = ""
        
        # # Code block for previous context and additional pages (currently disabled)
        # if not page_names and user_id and user_id in user_interactions:
        #     # Check if previous interaction is within the time window
        #     prev_interaction = user_interactions[user_id]
        #     current_time = time.time()
        #
        #     if (current_time - prev_interaction['timestamp']) <= INTERACTION_WINDOW:
        #         # Use previous pages if available
        #         page_names = prev_interaction['pages'].copy()  # Make a copy to avoid modifying the original
        #
        #         # Add previous context to the conversation
        #         previous_context = f"""
        #         Your previous question: {prev_interaction['query']}
        #
        #         My previous answer: {prev_interaction['response']}
        #
        #         I'll use the same wiki pages to answer your follow-up question.
        #         """
        #         print(f"Using previous context for user {user_id}")
        #
        #         # Try to identify additional wiki pages with the combined context
        #         if previous_context:
        #             combined_query = f"{user_query}\n\nContext from previous conversation: {prev_interaction['query']}\n{prev_interaction['response']}"
        #             print(f"Trying to identify additional wiki pages with combined context")
        #
        #             additional_pages = await identify_wiki_pages(combined_query, image_urls)
        #
        #             # Add any new pages that aren't already in the list
        #             if additional_pages:
        #                 for page in additional_pages:
        #                     if page not in page_names:
        #                         page_names.append(page)
        #                         print(f"Added additional wiki page from context: {page}")
        
        # Set up wiki_content and updated_page_names
        wiki_content = ""
        updated_page_names = []
        
        if page_names:
            print(f"Fetching wiki pages: {', '.join(page_names)}")
            
            # Fetch content from identified wiki pages
            wiki_content, redirects = await asyncio.to_thread(
                fetch_osrs_wiki_pages, page_names
            )
            
            # Update page_names with redirected names for correct source URLs
            for page in page_names:
                if page in redirects:
                    updated_page_names.append(redirects[page])
                else:
                    updated_page_names.append(page)
            
            print(f"Retrieved content from {len(page_names)} wiki pages")
            if redirects:
                print(f"Followed redirects: {redirects}")
        else:
            # No wiki pages identified, perform web search
            print("No wiki pages identified, performing web search...")
            
            # Get web search context
            wiki_content = await get_web_search_context(user_query)
            print("Using web search results as context")
        
        # Use text-based approach for response formatting
        # Function calling works for page identification but not for response formatting
        model = genai.GenerativeModel(config.gemini_flash_model)
        
        prompt = f"""
        {SYSTEM_PROMPT}
        
        {previous_context}
        
        User Query: {user_query}
        
        OSRS Wiki Information:
        {wiki_content}
        
        Provide a response following these specific formatting rules:
        1. Start with a **Section Header**
        2. Use * for list items (not bullet points)
        3. Bold ONLY:
           * Item names (e.g., **Abyssal whip**)
           * Monster/boss names (e.g., **Abyssal demon**)
           * Location names (e.g., **Wilderness**)
           * Section headers
        4. Do NOT bold:
           * Drop rates
           * Prices
           * Combat stats
           * Other numerical values
        5. Include sources at the end using the URL format: https://oldschool.runescape.wiki/w/[page_name]
        """
        response = await asyncio.to_thread(
            lambda: model.generate_content(prompt).text
        )
        
        # Store this interaction if user_id is provided
        if user_id:
            user_interactions[user_id] = {
                'timestamp': time.time(),
                'query': user_query,
                'response': response,
                'pages': page_names
            }
            print(f"Stored interaction for user {user_id}")
        
        # Import regex at the top level to avoid repeated imports
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
        
        # Check if the model has already generated a "Sources:" section
        # If found, cut off the response at that point
        sources_index = response.find("\n\nSources:")
        if sources_index == -1:
            sources_index = response.find("\nSources:")
        
        if sources_index != -1:
            # Cut off the response at the Sources line
            response = response[:sources_index].rstrip()
        
        # Now add our own source citations
        sources_added = False
        
        # Check if we have wiki pages
        if updated_page_names:
            sources = "\n\nSources:"
            for page in updated_page_names:
                # Clean the page name and add URL
                clean_page = page.replace(' ', '_').strip('[]')
                sources += f"\n- <https://oldschool.runescape.wiki/w/{clean_page}>"
            
            # Make sure the response with sources doesn't exceed Discord's limit
            if len(response) + len(sources) <= 1900:
                response += sources
                sources_added = True
        
        # Check if we have web search results
        elif "=== WEB SEARCH RESULTS ===" in wiki_content and not sources_added:
            # Extract URLs from the web search results
            source_urls = []
            source_pattern = re.compile(r'Source: <(https?://[^>]+)>')
            source_matches = source_pattern.findall(wiki_content)
            
            if source_matches:
                sources = "\n\nSources:"
                for url in source_matches:
                    sources += f"\n- <{url}>"
                
                # Make sure the response with sources doesn't exceed Discord's limit
                if len(response) + len(sources) <= 1900:
                    response += sources
                    sources_added = True
        
        # Now clean all URLs in the response, regardless of whether sources were added
        
        # First clean wiki URLs
        for page in updated_page_names:
            clean_page = page.replace(' ', '_').strip('[]')
            base_url = f"https://oldschool.runescape.wiki/w/{clean_page}"
            
            # Handle escaped underscores
            escaped_page = clean_page.replace('_', '\\_')
            escaped_url = f"https://oldschool.runescape.wiki/w/{escaped_page}"
            
            # Create a pattern that matches the problematic format with both escaped and unescaped versions
            pattern = r'\(\[' + re.escape(escaped_url) + r'\]\(<' + re.escape(base_url) + r'>\)\)'
            response = re.sub(pattern, f"(<{base_url}>)", response)
            
            # Handle special case for URLs with parentheses
            if '(' in clean_page and ')' in clean_page:
                # Extract the parts before and after the parenthesis
                before_paren = clean_page.split('(')[0]
                paren_part = '(' + clean_page.split('(')[1]
                
                # Create escaped versions for both parts
                escaped_before = before_paren.replace('_', '\\_')
                escaped_paren = paren_part.replace('_', '\\_')
                
                # Fix cases where the URL is broken with parentheses
                broken_pattern = f"(<https://oldschool.runescape.wiki/w/{before_paren}>_{paren_part})"
                correct_url = f"<https://oldschool.runescape.wiki/w/{clean_page}>"
                response = response.replace(broken_pattern, correct_url)
                
                # Also handle the escaped version
                broken_escaped = f"(<https://oldschool.runescape.wiki/w/{escaped_before}>\\_{escaped_paren})"
                response = response.replace(broken_escaped, correct_url)
            
            # Apply the cleaning function with both regular and escaped URLs
            response = clean_url_patterns(response, base_url, escaped_url)
        
        # Now find and clean all other URLs in the response
        # Common URL patterns - improved to better handle special characters
        url_pattern = re.compile(r'https?://[^\s<>"]+')
        
        # Find all URLs in the response
        all_urls = url_pattern.findall(response)
        
        # Clean each URL that's not already properly formatted
        for url in all_urls:
            # More precise check for properly formatted URLs with angle brackets
            if f"<{url}>" in response:
                continue
                
            # Skip URLs that are part of already properly formatted URLs
            # This prevents partial URL matching issues
            is_part_of_formatted_url = False
            for formatted_url in [f"<{u}>" for u in all_urls if len(u) > len(url)]:
                if formatted_url in response and url in formatted_url:
                    is_part_of_formatted_url = True
                    break
                    
            if is_part_of_formatted_url:
                continue
                
            # Clean the URL
            response = clean_url_patterns(response, url)
        
        return response[:1900] + "\n\n(Response length exceeded)" if len(response) > 1900 else response
        
    except Exception as e:
        print(f"Error processing query: {e}")
        return f"Error processing your query: {str(e)}"

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

        # Let the user know we're processing their request
        if image_urls:
            await ctx.send("Processing your image(s) and request, this may take a moment...")
        else:
            await ctx.send("Processing your request, this may take a moment...")

        try:
            # Get guild members to check if any are mentioned in the query
            guild_members = get_guild_members()
            mentioned_members = []
            
            # Check if any guild members are mentioned in the query (case insensitive)
            for member in guild_members:
                if member.lower() in user_query.lower():
                    mentioned_members.append(member)
            
            # If guild members are mentioned, fetch their data and use the player data processor
            if mentioned_members:
                # Fetch player details for each mentioned member
                player_data_list = []
                for member in mentioned_members:
                    player_data = fetch_player_details(member)
                    if player_data:
                        player_data_list.append(player_data)
                
                if player_data_list:
                    #await ctx.send(f"Found {len(player_data_list)} player(s) mentioned in your query. Processing...")
                    response = await process_player_data_query(user_query, player_data_list, image_urls)
                    await ctx.send(response)
                    return
            
            # If no members were found or player data couldn't be fetched, use the regular process
            response = await process_user_query(user_query or "What is this OSRS item?", image_urls, user_id)
            await ctx.send(response)
        except Exception as e:
            await ctx.send(f"Error processing your request: {str(e)}")
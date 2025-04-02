import asyncio
import aiohttp
from PIL import Image
import io
import time
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
SYSTEM_PROMPT = """
You are an Old School RuneScape (OSRS) expert assistant. Your task is to answer questions about OSRS using information provided from the OSRS Wiki.
If asked about yourself, you are YomiBot, an assistant created by CyanideByte for clan Mesa.

Content Rules:
1. Use only the provided wiki information and web search results when possible.
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

async def generate_search_term(query):
    """Use Gemini to generate a search term based on the user query or determine if no search is needed"""
    if not config.gemini_api_key:
        print("Gemini API key not set")
        return query
    
    try:
        model = genai.GenerativeModel(config.gemini_model)
        
        prompt = f"""
        You are an assistant that helps generate effective search terms for Old School RuneScape (OSRS) related queries.
        
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

async def process_player_data_query(user_query: str, player_data_list: list, image_urls: list[str] = None) -> str:
    """Process a user query with player data using Gemini"""
    if not config.gemini_api_key:
        return "Sorry, the OSRS player query assistant is not available because the Gemini API key is not set."
    
    try:
        model = genai.GenerativeModel(config.gemini_model)
        
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
        1. Use - for bullet points (they format correctly in Discord)
        2. Bold important information with **text**, such as:
           - Player names (e.g., **PlayerName**)
           - Boss or skill names
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
        
        # Set up variables for content and page tracking
        wiki_content = ""
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
                if page in redirects:
                    updated_page_names.append(redirects[page])
                else:
                    updated_page_names.append(page)
            
            print(f"Retrieved content from {len(wiki_page_names)} wiki pages")
            if redirects:
                print(f"Followed redirects: {redirects}")
        
        # If we have non-wiki sources, format them and append to wiki_content
        if non_wiki_sources:
            print(f"Adding {len(non_wiki_sources)} non-wiki sources to context")
            non_wiki_content = format_search_results(non_wiki_sources)
            wiki_content += non_wiki_content
        
        # If we have no content at all, perform a full web search
        if not wiki_content:
            print("No wiki pages identified, performing full web search...")
            
            # Get raw search results
            search_results = await get_web_search_context(user_query)
            
            # Format the results for use as context
            wiki_content = format_search_results(search_results)
            print("Using web search results as context")
        
        # Use text-based approach for response formatting
        # Function calling works for page identification but not for response formatting
        model = genai.GenerativeModel(config.gemini_model)
        
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
           - Item names (e.g., **Abyssal whip**)
           - Monster/boss names (e.g., **Abyssal demon**)
           - Location names (e.g., **Wilderness**)
           - Section headers
        4. Do NOT bold:
           - Drop rates
           - Prices
           - Combat stats
           - Other numerical values
        5. Include sources at the end using the URL format: https://oldschool.runescape.wiki/w/[page_name]
           - Start your sources section with "Sources:" and then list the URLs that were used to answer the question.
           - Only list sources that contained useful and relevant information for the answer.
           - Use the - symbol for bullet points in the sources section.
           - Wrap source in <> tags to suppress embedding in Discord.

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
        
        # Function to ensure all URLs in the Sources section have bullet points
        def format_sources_section(text):
            # Find the Sources section
            sources_patterns = ["\n\nSources:", "\nSources:", "\n\nSource:", "\nSource:"]
            sources_index = -1
            matched_pattern = ""
            
            for pattern in sources_patterns:
                if pattern in text:
                    sources_index = text.find(pattern)
                    matched_pattern = pattern
                    break
            
            if sources_index == -1:
                return text  # No Sources section found
            
            # Split the text into pre-sources and sources parts
            pre_sources = text[:sources_index]
            sources_part = text[sources_index:]
            
            # Split the sources part into lines
            sources_lines = sources_part.split('\n')
            formatted_sources_lines = [sources_lines[0]]  # Keep the "Sources:" header
            
            # Process each line after the header
            for i in range(1, len(sources_lines)):
                line = sources_lines[i].strip()
                
                # Skip empty lines
                if not line:
                    formatted_sources_lines.append('')
                    continue
                
                # Check if the line contains a URL
                if 'http' in line:
                    # Check if the line already has a bullet point
                    if not line.startswith('*') and not line.startswith('-') and not line.startswith('•'):
                        # Add a bullet point with asterisk
                        line = f"* {line}"
                
                formatted_sources_lines.append(line)
            
            # Combine everything back
            return pre_sources + '\n'.join(formatted_sources_lines)
        
        # Check if the model has already generated a "Sources:" or "Source:" section
        has_sources_section = False
        sources_patterns = ["\n\nSources:", "\nSources:", "\n\nSource:", "\nSource:"]
        
        for pattern in sources_patterns:
            if pattern in response:
                has_sources_section = True
                # Format the existing Sources section
                response = format_sources_section(response)
                break
        
        # Extract all URLs already in the response
        existing_urls = []
        url_pattern = re.compile(r'<(https?://[^\s<>"]+)>')
        existing_urls = url_pattern.findall(response)
        
        # Now add our own source citations if there's no existing sources section
        sources_added = False
        
        if not has_sources_section:
            # Check if we have wiki pages
            if updated_page_names:
                sources = "\n\nSources:"
                urls_to_add = []
                
                for page in updated_page_names:
                    # Clean the page name and create URL
                    clean_page = page.replace(' ', '_').strip('[]')
                    url = f"https://oldschool.runescape.wiki/w/{clean_page}"
                    
                    # Only add URLs that aren't already in the response
                    if url not in existing_urls:
                        urls_to_add.append(url)
                        sources += f"\n* <{url}>"  # Use asterisk instead of hyphen
                
                # Make sure the response with sources doesn't exceed Discord's limit
                # Only add sources if we have new URLs to add
                if urls_to_add and len(response) + len(sources) <= 1900:
                    response += sources
                    sources_added = True
            
            # Check if we have web search results
            elif "=== WEB SEARCH RESULTS ===" in wiki_content and not sources_added:
                # Extract URLs from the web search results
                source_urls = []
                source_pattern = re.compile(r'Source: <(https?://[^>]+)>')
                source_matches = source_pattern.findall(wiki_content)
                
                if source_matches:
                    urls_to_add = []
                    sources = "\n\nSources:"
                    
                    for url in source_matches:
                        # Only add URLs that aren't already in the response
                        if url not in existing_urls:
                            urls_to_add.append(url)
                            sources += f"\n* <{url}>"  # Use asterisk instead of hyphen
                    
                    # Make sure the response with sources doesn't exceed Discord's limit
                    # Only add sources if we have new URLs to add
                    if urls_to_add and len(response) + len(sources) <= 1900:
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
        # More aggressive URL detection and wrapping
        # This pattern matches URLs that are not already wrapped in angle brackets
        # It handles URLs in various contexts, including in bullet points and after hyphens
        unwrapped_url_pattern = re.compile(r'(?<!\<)(https?://[^\s<>"]+)(?!\>)')
        
        # Replace all unwrapped URLs with wrapped versions
        response = unwrapped_url_pattern.sub(r'<\1>', response)
        
        # Additional pass to handle any URLs that might have been missed
        # This is a more targeted approach for specific contexts
        url_pattern = re.compile(r'https?://[^\s<>"]+')
        all_urls = url_pattern.findall(response)
        
        for url in all_urls:
            # Skip URLs that are already properly formatted
            if f"<{url}>" in response:
                continue
                
            # Skip URLs that are part of already properly formatted URLs
            is_part_of_formatted_url = False
            for formatted_url in [f"<{u}>" for u in all_urls if len(u) > len(url)]:
                if formatted_url in response and url in formatted_url:
                    is_part_of_formatted_url = True
                    break
                    
            if is_part_of_formatted_url:
                continue
                
            # Clean the URL using our existing function
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

        # Let the user know we're processing their request and store the message object
        if image_urls:
            processing_msg = await ctx.send("Processing your image(s) and request, this may take a moment...")
        else:
            processing_msg = await ctx.send("Processing your request, this may take a moment...")

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
                    await processing_msg.edit(content=response)
                    return
            
            # If no members were found or player data couldn't be fetched, use the regular process
            response = await process_user_query(user_query or "What is this OSRS item?", image_urls, user_id)
            await processing_msg.edit(content=response)
        except Exception as e:
            # If there was an error, edit the processing message with the error
            await processing_msg.edit(content=f"Error processing your request: {str(e)}")
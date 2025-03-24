import asyncio
import aiohttp
from PIL import Image
import io
import google.generativeai as genai
from config.config import config

# Import wiki-related functions from wiki.py
from osrs.wiki import fetch_osrs_wiki_pages
# Import player tracking functions from tracker.py
from wiseoldman.tracker import get_guild_members, fetch_player_details, format_player_data

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

        Query: {user_query}
        
        Respond ONLY with page names separated by commas. No additional text.
        Example: "Dragon_scimitar,Abyssal_whip"
        """
        
        generation = await asyncio.to_thread(
            lambda: model.generate_content(prompt)
        )
        page_names = [name.strip() for name in generation.text.split(',') if name.strip()]
        print(f"Identified wiki pages: {page_names}")
        return page_names
        
    except Exception as e:
        print(f"Error identifying wiki pages: {e}")
        return []

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

async def process_user_query(user_query: str, image_urls: list[str] = None) -> str:
    """Process a user query about OSRS using Gemini and the OSRS Wiki, optionally with images"""
    if not config.gemini_api_key:
        return "Sorry, the OSRS Wiki assistant is not available because the Gemini API key is not set."
        
    try:
        # Identify relevant wiki pages, potentially using image analysis
        page_names = await identify_wiki_pages(user_query, image_urls)
        
        if not page_names:
            return "I couldn't determine which wiki pages to search. Please try rephrasing your query to be more specific about OSRS content."
        
        print(f"Fetching wiki pages: {', '.join(page_names)}")
        
        # Fetch content from identified wiki pages
        wiki_content, redirects = await asyncio.to_thread(
            fetch_osrs_wiki_pages, page_names
        )
        
        # Update page_names with redirected names for correct source URLs
        updated_page_names = []
        for page in page_names:
            if page in redirects:
                updated_page_names.append(redirects[page])
            else:
                updated_page_names.append(page)
        
        print(f"Retrieved content from {len(page_names)} wiki pages")
        if redirects:
            print(f"Followed redirects: {redirects}")
        
        # Use text-based approach for response formatting
        # Function calling works for page identification but not for response formatting
        model = genai.GenerativeModel(config.gemini_model)
        
        prompt = f"""
        {SYSTEM_PROMPT}
        
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
        
        # Add source citations if not already included
        if not any(f"https://oldschool.runescape.wiki/w/{page.replace(' ', '_')}" in response for page in updated_page_names):
            sources = "\n\nSources:"
            for page in updated_page_names:
                # Clean the page name and add URL
                clean_page = page.replace(' ', '_').strip('[]')
                sources += f"\n- <https://oldschool.runescape.wiki/w/{clean_page}>"
            
            # Make sure the response with sources doesn't exceed Discord's limit
            if len(response) + len(sources) <= 1990:
                response += sources
        else:
            # Clean any URLs in the response to use angle brackets
            for page in updated_page_names:
                clean_page = page.replace(' ', '_').strip('[]')
                base_url = f"https://oldschool.runescape.wiki/w/{clean_page}"
                # Handle various URL patterns
                patterns = [
                    (f"[{base_url}]({base_url})", base_url),  # Markdown style
                    (f"[<{base_url}>]", base_url),  # Bracketed angle brackets
                    (f"(<{base_url}>)", base_url),  # Parenthesized angle brackets
                    (f"[{base_url}]", base_url),  # Simple brackets
                ]
                # First remove any special formatting
                for pattern, replacement in patterns:
                    response = response.replace(pattern, replacement)
                # Then add the single angle brackets if the URL is bare
                response = response.replace(base_url, f"<{base_url}>")
        
        return response
        
    except Exception as e:
        print(f"Error processing query: {e}")
        return f"Error processing your query: {str(e)}"

# Discord command registration - depends on wiki functionality
def register_commands(bot):
    @bot.command(name='askyomi', aliases=['yomi', 'ask'])
    async def askyomi(ctx, *, user_query: str = ""):
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
            response = await process_user_query(user_query or "What is this OSRS item?", image_urls)
            await ctx.send(response)
        except Exception as e:
            await ctx.send(f"Error processing your request: {str(e)}")
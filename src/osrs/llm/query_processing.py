import asyncio
import time
import re
import google.generativeai as genai
from config.config import config
from osrs.llm.identification import identify_and_fetch_players, identify_and_fetch_wiki_pages, is_player_only_query
from osrs.llm.source_management import ensure_all_sources_included, clean_url_patterns
from osrs.wiseoldman import format_player_data

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

async def process_unified_query(
    user_query: str,
    user_id: str = None,
    image_urls: list[str] = None,
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
        player_task = identify_and_fetch_players(user_query, requester_name=requester_name)
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
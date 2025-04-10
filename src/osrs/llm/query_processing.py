import asyncio
import time
import re
import google.generativeai as genai
from config.config import config
from osrs.llm.identification import (
    identify_and_fetch_players,
    identify_and_fetch_wiki_pages,
    identify_and_fetch_metrics,
    is_player_only_query,
    is_prohibited_query,
    is_wiki_only_query
)
from osrs.llm.source_management import ensure_all_sources_included, clean_url_patterns
from osrs.wiseoldman import format_player_data, format_metrics

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
    requester_name: str = None,
    status_message = None
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
        
        # First, check if query is about prohibited topics
        is_prohibited = await is_prohibited_query(user_query)
        if is_prohibited:
            # Generate security explanation using Gemini
            model = genai.GenerativeModel(config.gemini_model)
            prompt = f"""
            The user asked: "{user_query}"
            
            You must write a response that explains the SPECIFIC security risks of their query. DO NOT give a generic response about all prohibited topics.

            For RWT (gold/account/services):
            - Focus on account theft/recovery scams
            - Permanent bans from Jagex
            - Credit card fraud risks
            
            For botting clients:
            - Focus on malware/keyloggers
            - Account hijacking
            - Resource theft
            
            For unofficial clients:
            - Focus on password stealing
            - Bank PIN capture
            - Authentication bypass risks
            
            For private servers:
            - Focus on malware from downloads
            - Account database theft
            - Reused password risks

            Write a focused response ONLY about the specific topic they asked about. Keep it under 500 characters.
            """
            
            generation = await asyncio.to_thread(
                lambda: model.generate_content(prompt)
            )
            explanation = None
            if generation and generation.text:
                explanation = generation.text.strip()
            
            # Fallback if generation fails
            if not explanation:
                explanation = "This topic poses serious security risks to your RuneScape account and computer. For your safety, please only use the official RuneScape client and avoid prohibited activities like RWT, botting, and private servers."
            if generation and generation.text:
                explanation = generation.text.strip()
            
            if status_message:
                await status_message.edit(content=explanation)
            return explanation

        # If not prohibited, proceed with player data
        if status_message:
            await status_message.edit(content="Finding players...")
            
        player_task = identify_and_fetch_players(user_query, requester_name=requester_name)
        player_data_list, player_sources, is_all_members = await player_task
        
        # If query is about all members, fetch metrics data
        metrics_data = {}
        if is_all_members:
            if status_message:
                await status_message.edit(content="Fetching clan metrics...")
            
            metrics_task = identify_and_fetch_metrics(user_query)
            metrics_data = await metrics_task
            
            # Format metrics data for display
            metrics_context = format_metrics(metrics_data)
            
            # Use metrics data to generate response
            model = genai.GenerativeModel(config.gemini_model)
            
            prompt = f"""
            {UNIFIED_SYSTEM_PROMPT}
            
            User Query: {user_query}
            
            Clan Metrics Data:
            {metrics_context}
            
            This query is about clan-wide metrics. Use the provided metrics data to answer the query.
            Do not speculate about information not present in the metrics data.
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
                 - <https://wiseoldman.net/groups/3773/hiscores>
               
               - Do NOT add empty lines between sources
               - Do NOT include duplicate URLs in the sources section
               - Include ALL relevant sources
               - The "Sources:" header is ABSOLUTELY REQUIRED for ALL responses
               - NEVER list URLs without the "Sources:" header
            """
            
            try:
                if status_message:
                    await status_message.edit(content="Generating response...")
                    
                generation = await asyncio.to_thread(
                    lambda: model.generate_content(prompt)
                )
                if generation is None:
                    raise ValueError("Gemini model returned None")
                if not generation.text:
                    raise ValueError("Gemini model returned empty response")
                response = generation.text.strip()
                if not response:
                    raise ValueError("Gemini model returned whitespace-only response")
                
                # Build sources for each metric
                sources_section = "\n\nSources:"
                for metric_name in metrics_data.keys():
                    source_url = f"https://wiseoldman.net/groups/3773/hiscores?metric={metric_name}"
                    sources_section += f"\n- <{source_url}>"

                # Ensure response has "Sources:" section with all metric URLs
                if "Sources:" not in response:
                    response += sources_section
                else:
                    # Replace existing sources section with our metric-specific sources
                    response = re.sub(r'\n\nSources:.*$', sources_section, response, flags=re.DOTALL)
                
                # Clean URLs
                for metric_name in metrics_data.keys():
                    source_url = f"https://wiseoldman.net/groups/3773/hiscores?metric={metric_name}"
                    response = clean_url_patterns(response, source_url)
                
                # Truncate if too long for Discord
                response = response[:1900] + "\n\n(Response length exceeded)" if len(response) > 1900 else response
                
                # Update status message with final response
                if status_message:
                    await status_message.edit(content=response)
                    
                return response
                
            except Exception as e:
                print(f"Failed to generate metrics response: {e}")
                return f"Error: Failed to generate metrics response - {str(e)}"
        
        # Determine if this is a player-only query
        is_player_only = False
        if player_data_list:
            is_player_only = True # If any players were identified, always skip wiki/web search
            # if status_message:
            #     await status_message.edit(content="Analyzing query...")
                
            # is_player_only = await is_player_only_query(user_query, player_data_list)
            # print(f"Query determined to be player-only: {is_player_only}")
        
        # Only fetch wiki/web content if this is not a player-only query
        if not is_player_only:
            if status_message:
                await status_message.edit(content="Searching wiki...")
            wiki_task = identify_and_fetch_wiki_pages(user_query, image_urls, status_message)
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
        
        # Format player data and track valid players for sources
        player_context = ""
        valid_players = []
        if player_data_list:
            for player_data in player_data_list:
                formatted_data = format_player_data(player_data)
                if formatted_data is not None:
                    player_name = player_data.get('displayName', 'Unknown player')
                    player_context += f"\n===== {player_name} DATA =====\n"
                    player_context += formatted_data
                    player_context += "\n\n"
                    valid_players.append(player_data)
            print(f"Formatted data for {len(valid_players)} out of {len(player_data_list)} players")
        
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
        try:
            if status_message:
                await status_message.edit(content="Generating response...")
                
            generation = await asyncio.to_thread(
                lambda: model.generate_content(prompt)
            )
            if generation is None:
                raise ValueError("Gemini model returned None")
            if not generation.text:
                raise ValueError("Gemini model returned empty response")
            response = generation.text.strip()
            if not response:
                raise ValueError("Gemini model returned whitespace-only response")
                
            # For player-only queries, ensure response has "Sources:" section
            if is_player_only and "Sources:" not in response:
                response += "\n\nSources:"
                
        except Exception as e:
            print(f"Failed to generate response: {e}")
            return f"Error: Failed to generate response - {str(e)}"
        response_time = time.time() - response_start_time
        print(f"Generated response in {response_time:.2f} seconds")
        # Filter sources to only include valid players
        valid_player_sources = [
            source for source in player_sources
            if any(p.get('displayName', '').lower() == source.get('name', '').lower() for p in valid_players)
        ]
        
        # For player-only queries, simplify source handling
        if is_player_only:
            # Build sources section with just valid player sources
            sources_section = "\n\nSources:"
            for source in valid_player_sources:
                if 'url' in source:
                    sources_section += f"\n- <{source['url']}>"
            
            # Replace or append sources section
            if "Sources:" in response:
                # Replace entire sources section
                response = re.sub(r'\n\nSources:.*$', sources_section, response, flags=re.DOTALL)
            else:
                response += sources_section
        else:
            # Normal source handling for non-player-only queries
            response = ensure_all_sources_included(response, valid_player_sources, wiki_sources, web_sources)
        
        
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
        response = response[:1900] + "\n\n(Response length exceeded)" if len(response) > 1900 else response
        
        # Update status message with final response
        if status_message:
            await status_message.edit(content=response)
            
        return response
        
    except Exception as e:
        print(f"Error processing unified query: {e}")
        return f"Error processing your query: {str(e)}"

async def roast_player(player_data):
    """
    Generate a humorous roast for a player based on their stats
    """
    if not config.gemini_api_key:
        return "Sorry, the player roast feature is not available because the Gemini API key is not set."
    
    if not player_data or 'displayName' not in player_data:
        return None
        
    try:
        model = genai.GenerativeModel(config.gemini_model)
        
        # Format player data for context
        try:
            player_context = format_player_data(player_data)
            if not player_context:
                return None
        except Exception as e:
            print(f"Error formatting player data: {e}")
            return None
            
        player_name = player_data.get('displayName', 'Unknown player')
        
        prompt = f"""
        You are a ruthless and savage OSRS player who absolutely destroys noobs based on their stats. Your task is to brutally roast this player by pointing out everything wrong with their account.
        
        Rules for the roast:
        1. ONLY focus on negatives - low skills, pathetic boss KC's, and embarrassingly high time spent on easy content
        2. The roast must be ONE savage paragraph (not bullet points)
        3. Savage comparisons are encouraged (e.g. "a level 3 bot has better stats")
        4. Mock any high KC's in easy bosses while pointing out zero KC's in real content
        5. Ridicule high levels in easy skills while roasting their terrible levels in actual challenging skills
        6. Use words like "pathetic", "embarrassing", "terrible", "laughable"
        7. End with a devastating final punch

        Player Name: {player_name}
        
        Player Stats:
        {player_context}
        
        Generate a single paragraph roast focusing on the player's noob-like stats or achievements.
        """
        
        try:
            generation = await asyncio.to_thread(
                lambda: model.generate_content(prompt)
            )
            if generation is None:
                return None
            if not generation.text:
                return None
            response = generation.text.strip()
            if not response:
                return None
                
            # Format the response for Discord
            formatted_response = f"**Roast of {player_name}**\n\n{response}"
            return formatted_response
            
        except Exception as e:
            print(f"Error in model generation: {e}")
            return None
            
    except Exception as e:
        print(f"Error generating player roast: {e}")
        return None
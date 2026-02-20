import asyncio
import time
import re
from config.config import config
from osrs.llm.llm_service import llm_service, LLMServiceError
from osrs.llm.identification_optimized import identify_and_fetch_all_optimized
from osrs.llm.source_management import ensure_all_sources_included, clean_url_patterns
from osrs.wiseoldman import format_player_data, format_metrics
from osrs.wiseoldman import get_guild_members_data

# Token counting
try:
    import tiktoken
    encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding (good approximation for Gemini)

    def count_tokens(text: str) -> int:
        """Count tokens in text using tiktoken."""
        if not text:
            return 0
        return len(encoding.encode(text))

    def count_messages_tokens(messages: list) -> int:
        """Count tokens in a list of messages."""
        total = 0
        for msg in messages:
            total += count_tokens(msg.get("content", ""))
            total += count_tokens(msg.get("role", ""))
        return total
except ImportError:
    # Fallback if tiktoken not available
    def count_tokens(text: str) -> int:
        """Rough token count (1 token ≈ 4 chars)."""
        if not text:
            return 0
        return len(text) // 4

    def count_messages_tokens(messages: list) -> int:
        """Rough token count for messages."""
        return sum(count_tokens(str(msg)) for msg in messages)

# System prompt for Gemini
# Unified system prompt for both player data and wiki information
UNIFIED_SYSTEM_PROMPT = """
You are an Old School RuneScape (OSRS) expert assistant. Your task is to answer questions about OSRS using:
1. Player data from WiseOldMan when provided
2. OSRS Wiki information when available
3. Web search results when necessary

Notes:
1. When players refer to a "quiver" or "colosseum", they are referring to the "sol_heredit" metric on WiseOldMan, which is the boss that drops the dizana's quiver.
2. When players refer to "infernal cape", they are referring to the "tzkal_zuk" metric on WiseOldMan, which is the boss that drops the infernal cape.
3. Sailing is a new skill in OSRS, it is already released.

Content Rules:
1. Use only the provided information sources when possible
2. If player data is available, analyze it thoroughly to answer player-specific questions
3. If wiki/web information is available, use it to answer game mechanic questions
4. When appropriate, combine player data with wiki information for comprehensive answers
5. Prioritize key information the player needs
6. Format information clearly and consistently
7. Break information into clear sections
8. Keep answers concise (under 2,000 characters)
9. If you use any external sources (wiki, player data, web search), include a "Sources:" section at the end with all source URLs. If you don't use any external sources, do not include a Sources section.

Remember: Create clear, easy-to-read responses that focus on the key information.
"""

# Formatting rules used in multiple places
FORMATTING_RULES = """

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
5. Use comma notation for numbers over a million (e.g., "1,234,567" instead of "1234567")
6. If you use external sources (wiki, player data, web search), include sources at the end of your response:
   - Start a new paragraph with the exact text "Sources:" (including the colon)
   - The "Sources:" header MUST be on its own line
   - List each source URL on its own line with a hyphen (-) bullet point
   - Format ALL sources consistently as: "- <URL>" (no prefixes like "Player data:")
   - Example:

     Sources:
     - <https://oldschool.runescape.wiki/w/Abyssal_whip>
     - <https://wiseoldman.net/players/playername>

   - Do NOT add empty lines between sources
   - Do NOT include duplicate URLs in the sources section
   - Include ALL relevant sources
   - ONLY include a Sources section if you actually used external sources
   - If answering from general knowledge without sources, skip the Sources section entirely
"""

async def process_unified_query(
    user_query: str,
    user_id: str = None,
    image_urls: list[str] = None,
    requester_name: str = None,
    status_message = None,
    think: bool = False
) -> str:
    """
    OPTIMIZED version of process_unified_query using parallel tool calling.

    Reduces LLM calls from 4-5 to just 2:
    1. Single parallel identification call (players, wiki pages, metrics, classification)
    2. Final response generation

    Enable with: USE_OPTIMIZED_WORKFLOW=true in .env or config.use_optimized_workflow = True
    """
    print("\n" + "=" * 70)
    print("[OPTIMIZED WORKFLOW] Using parallel tool calling")
    print("=" * 70)

    if not config.gemini_api_key:
        return "Sorry, the OSRS assistant is not available because no LLM is configured."

    start_time = time.time()

    try:
        # ========================================================================
        # STEP 1: UNIFIED IDENTIFICATION (single LLM call with parallel tools)
        # ========================================================================
        if status_message:
            await status_message.edit(content="Analyzing query...")

        print("\n[STEP 1/2] Unified Identification")

        # Get guild members
        guild_members_data = get_guild_members_data()
        guild_member_names = [member['player']['displayName'] for member in guild_members_data]

        # Single parallel call that identifies EVERYTHING
        print(f"  Calling unified_identification for: '{user_query[:80]}...'")

        identification_result = await identify_and_fetch_all_optimized(
            user_query=user_query,
            guild_members=guild_member_names,
            requester_name=requester_name,
            status_message=status_message
        )

        # Extract results and timing
        identified_players = identification_result[0]
        wiki_pages = identification_result[1]
        is_all_members = identification_result[2]
        metrics = identification_result[3]
        search_queries = identification_result[4]
        identification_time = identification_result[5] if len(identification_result) > 5 else 0.0

        print(f"  Results: {len(identified_players)} players, {len(wiki_pages)} wiki pages, "
              f"{len(metrics)} metrics, {len(search_queries)} search queries, all_members={is_all_members}")

        # ========================================================================
        # STEP 2: Fetch data and generate response
        # ========================================================================
        print("\n[STEP 2/2] Fetching data and generating response")

        # Player data
        player_data_list = []
        player_sources = []

        if identified_players or is_all_members:
            if status_message:
                await status_message.edit(content="Fetching player data...")

            # Import here to avoid circular dependency
            from osrs.wiseoldman import fetch_player_details
            import aiohttp

            # Fetch player data (reuse existing logic but with pre-identified players)
            if is_all_members:
                # All members case - fetch metrics instead
                if status_message:
                    await status_message.edit(content="Fetching clan metrics...")

                print("  Fetching metrics for all clan members...")
                metrics_data = {}
                for metric in metrics:
                    try:
                        from osrs.wiseoldman import fetch_metric
                        scoreboard = fetch_metric(metric)
                        metrics_data[metric] = scoreboard
                    except Exception as e:
                        print(f"    Error fetching {metric}: {e}")

                # Generate metrics response
                metrics_context = format_metrics(metrics_data)

                prompt = f"""
                {UNIFIED_SYSTEM_PROMPT}

                User Query: {user_query}

                Clan Metrics Data:
                {metrics_context}

                This query is about clan-wide metrics. Use the provided metrics data to answer the query.
                Do not speculate about information not present in the metrics data.
                {FORMATTING_RULES}
                """

                if status_message:
                    await status_message.edit(content="Generating response...")

                print("[API CALL: LITELLM] metrics data generation")
                prompt_tokens = count_tokens(prompt)
                print(f"  [TOKENS] Prompt: {prompt_tokens:,} tokens")
                print(f"  [TOKENS] Metrics data: {count_tokens(str(metrics_data)):,} tokens")
                response = await llm_service.generate_text(prompt)
                response_tokens = count_tokens(response) if response else 0
                print(f"  [TOKENS] Response: {response_tokens:,} tokens")
                print(f"  [TOKENS] Total: {prompt_tokens + response_tokens:,} tokens")

                # Build sources - only if we have metrics data
                if metrics_data:
                    sources_section = "\n\nSources:"
                    for metric_name in metrics_data.keys():
                        source_url = f"https://wiseoldman.net/groups/3773/hiscores?metric={metric_name}"
                        sources_section += f"\n- <{source_url}>"

                    if "Sources:" not in response:
                        response += sources_section
                    else:
                        response = re.sub(r'\n\nSources:.*$', sources_section, response, flags=re.DOTALL)

                # Clean URLs
                for metric_name in metrics_data.keys():
                    source_url = f"https://wiseoldman.net/groups/3773/hiscores?metric={metric_name}"
                    response = clean_url_patterns(response, source_url)

                # Remove empty Sources sections
                response = re.sub(r'\n\nSources:\s*$', '', response.strip())

                if status_message and len(response) > 1900:
                    await send_long_response(status_message, response)
                else:
                    if status_message:
                        await status_message.edit(content=response)

                return response

            # Specific players case
            elif identified_players:
                print(f"  Fetching data for {len(identified_players)} players...")
                player_fetch_start = time.perf_counter()
                async with aiohttp.ClientSession() as session:
                    tasks = []
                    for player_name in identified_players:
                        # Find matching member data
                        member_data = next(
                            (m['player'] for m in guild_members_data if m['player']['displayName'] == player_name),
                            None
                        )
                        if member_data:
                            tasks.append(fetch_player_details(member_data, session))

                    if tasks:
                        player_data_results = await asyncio.gather(*tasks)

                        for player_name, player_data in zip(identified_players, player_data_results):
                            if player_data:
                                player_data_list.append(player_data)
                                player_url = f"https://wiseoldman.net/players/{player_name.lower().replace(' ', '_')}"
                                player_sources.append({
                                    'type': 'wiseoldman',
                                    'name': player_name,
                                    'url': player_url
                                })

                player_fetch_time = time.perf_counter() - player_fetch_start
                print(f"  Successfully fetched {len(player_data_list)} players in {player_fetch_time:.2f}s")

        # Wiki data (only if not player-only)
        wiki_content = ""
        wiki_sources = []
        web_sources = []

        # Track content sizes for logging
        initial_wiki_content = ""
        additional_wiki_content = ""
        web_search_content = ""

        if wiki_pages and not player_data_list:
            if status_message:
                await status_message.edit(content="Fetching wiki data...")

            print(f"  Fetching {len(wiki_pages)} wiki pages: {wiki_pages}")

            # Import wiki fetch function
            from osrs.wiki import fetch_osrs_wiki_pages
            from osrs.search import search_web, format_search_results

            # Fetch wiki content
            wiki_fetch_start = time.perf_counter()
            wiki_content, redirects, rejected_pages = await fetch_osrs_wiki_pages(wiki_pages)
            wiki_fetch_time = time.perf_counter() - wiki_fetch_start
            initial_wiki_content = wiki_content  # Track initial wiki content
            print(f"  Fetched wiki pages in {wiki_fetch_time:.2f}s")

            # Build wiki sources
            for page in wiki_pages:
                normalized_page = page.replace(' ', '_')
                redirected_page = redirects.get(normalized_page, normalized_page)
                final_page_name = redirected_page.replace(' ', '_')

                if final_page_name not in rejected_pages:
                    wiki_url = f"https://oldschool.runescape.wiki/w/{final_page_name}"
                    wiki_sources.append({
                        'type': 'wiki',
                        'name': final_page_name,
                        'url': wiki_url
                    })

            # Web search for additional queries
            if search_queries:
                if status_message:
                    await status_message.edit(content="Searching the web...")

                print(f"  Performing {len(search_queries)} web searches...")
                for query in search_queries:
                    print(f"    - Query: '{query}'")
                web_search_start = time.perf_counter()
                try:
                    all_search_results = []
                    for search_query in search_queries:
                        # Search the web directly with the query from unified_identification
                        search_results = await search_web(search_query)
                        all_search_results.extend(search_results)

                    for result in all_search_results:
                        url = result.get('url', '')

                        if "oldschool.runescape.wiki/w/" in url:
                            page_name = url.split("/w/")[-1].replace(' ', '_')
                            if not any(existing.lower() == page_name.lower() for existing in [s.get('name', '') for s in wiki_sources]):
                                additional_content, add_redirects, add_rejected = await fetch_osrs_wiki_pages([page_name])
                                if additional_content and page_name not in add_rejected:
                                    additional_wiki_content += "\n" + additional_content  # Track additional wiki
                                    wiki_content += "\n" + additional_content
                                    redirected_page = add_redirects.get(page_name, page_name)
                                    final_page_name = redirected_page.replace(' ', '_')
                                    wiki_sources.append({
                                        'type': 'wiki',
                                        'name': final_page_name,
                                        'url': f"https://oldschool.runescape.wiki/w/{final_page_name}"
                                    })
                        else:
                            web_sources.append({
                                'type': 'web',
                                'title': result.get('title', 'Web Source'),
                                'url': url
                            })

                    if web_sources:
                        web_content = format_search_results(all_search_results)
                        web_search_content = web_content  # Track web search content
                        if wiki_content:
                            wiki_content += "\n\n" + web_content
                        else:
                            wiki_content = web_content

                    web_search_time = time.perf_counter() - web_search_start
                    print(f"  Web search completed in {web_search_time:.2f}s")

                except Exception as e:
                    web_search_time = time.perf_counter() - web_search_start
                    print(f"    Web search error: {e} (after {web_search_time:.2f}s)")

        # ========================================================================
        # STEP 4: Generate final response
        # ========================================================================
        print("\n[FINAL RESPONSE] Generating response...")

        # Format player data
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

        # Build prompt
        if player_data_list:
            # Player-only query
            prompt = f"""
            You are an Old School RuneScape (OSRS) expert assistant. Your task is to answer questions about OSRS players using the provided player data.

            User Query: {user_query}

            Player Data:
            {player_context}

            This query can be answered using ONLY the player data provided. Do not speculate about information not present in the player data.
            {FORMATTING_RULES}
            """
        else:
            # Mixed or wiki-only query
            prompt = f"""
            {UNIFIED_SYSTEM_PROMPT}

            Today's date is: {time.strftime('%A %B %d, %Y')}

            User Query: {user_query}
            """

            if player_context:
                prompt += f"""

                Player Data:
                {player_context}
                """

            if wiki_content:
                prompt += f"""

                OSRS Wiki and Web Information:
                {wiki_content}
                """

            prompt += FORMATTING_RULES

        # Generate response
        if status_message:
            await status_message.edit(content="Generating response...")

        print("[API CALL: LITELLM] final response generation")
        generation_start = time.perf_counter()

        prompt_tokens = count_tokens(prompt)
        print(f"  [TOKENS] Prompt: {prompt_tokens:,} tokens")

        # Log content sizes with breakdown
        if initial_wiki_content:
            wiki_tokens = count_tokens(initial_wiki_content)
            print(f"  [TOKENS] Initial wiki pages: {wiki_tokens:,} tokens")
        if additional_wiki_content:
            add_tokens = count_tokens(additional_wiki_content)
            print(f"  [TOKENS] Additional wiki (from web): {add_tokens:,} tokens")
        if web_search_content:
            web_tokens = count_tokens(web_search_content)
            print(f"  [TOKENS] Web search results: {web_tokens:,} tokens")
        if player_data_list:
            player_tokens = count_tokens(str(player_data_list))
            print(f"  [TOKENS] Player data: {player_tokens:,} tokens")

        # Show total context
        total_context = (
            (len(initial_wiki_content) if initial_wiki_content else 0) +
            (len(additional_wiki_content) if additional_wiki_content else 0) +
            (len(web_search_content) if web_search_content else 0) +
            (len(str(player_data_list)) if player_data_list else 0)
        )
        print(f"  [TOKENS] Total context: {count_tokens(str(total_context)):,} tokens (estimated)")

        response = await llm_service.generate_text(prompt)
        generation_time = time.perf_counter() - generation_start
        response_tokens = count_tokens(response) if response else 0
        print(f"  [TOKENS] Response: {response_tokens:,} tokens")
        print(f"  [TIMING] Generation completed in {generation_time:.2f}s")
        print(f"  [TOKENS] Total: {prompt_tokens + response_tokens:,} tokens")

        if response is None:
            return "Error: Failed to generate response"
        response = response.strip()
        if not response:
            return "Error: Empty response generated"

        # Add sources
        valid_player_sources = [
            source for source in player_sources
            if any(p.get('displayName', '').lower() == source.get('name', '').lower() for p in valid_players)
        ]

        if player_data_list and valid_player_sources:
            sources_section = "\n\nSources:"
            for source in valid_player_sources:
                if 'url' in source:
                    sources_section += f"\n- <{source['url']}>"

            if "Sources:" in response:
                response = re.sub(r'\n\nSources:.*$', sources_section, response, flags=re.DOTALL)
            else:
                response += sources_section
        else:
            response = ensure_all_sources_included(response, valid_player_sources, wiki_sources, web_sources)

        # Clean URLs
        for source in wiki_sources:
            url = source['url']
            clean_page = source['name'].replace(' ', '_')
            escaped_page = clean_page.replace('_', '\\_')
            escaped_url = f"https://oldschool.runescape.wiki/w/{escaped_page}"
            response = clean_url_patterns(response, url, escaped_url)

        for source in player_sources:
            url = source['url']
            response = clean_url_patterns(response, url)

        for source in web_sources:
            url = source['url']
            response = clean_url_patterns(response, url)

        # Clean any remaining URLs
        unwrapped_url_pattern = re.compile(r'(?<!\<)(https?://[^\s<>"]+)(?!\>)')
        response = unwrapped_url_pattern.sub(r'<\1>', response)

        # Remove empty Sources sections (LLM might generate "Sources:" with nothing after)
        response = re.sub(r'\n\nSources:\s*$', '', response.strip())

        # Log timing breakdown
        total_time = time.time() - start_time
        print(f"\n[TIMING BREAKDOWN]")
        print(f"  Total query time: {total_time:.2f}s")
        print(f"  - Unified identification: {identification_time:.2f}s ({identification_time/total_time*100:.1f}% of total)")
        if 'player_fetch_time' in locals():
            print(f"  - Player data fetching: {player_fetch_time:.2f}s ({player_fetch_time/total_time*100:.1f}%)")
        if 'wiki_fetch_time' in locals():
            print(f"  - Wiki page fetching: {wiki_fetch_time:.2f}s ({wiki_fetch_time/total_time*100:.1f}%)")
        if 'web_search_time' in locals():
            print(f"  - Web search: {web_search_time:.2f}s ({web_search_time/total_time*100:.1f}%)")
        if 'generation_time' in locals():
            print(f"  - Final LLM generation: {generation_time:.2f}s ({generation_time/total_time*100:.1f}%)")

        print(f"\n[OPTIMIZED WORKFLOW] Completed in {total_time:.2f} seconds")
        print(f"                      (vs ~8-10s with old workflow)")
        print("=" * 70)

        # Send response
        if status_message and len(response) > 1900:
            await send_long_response(status_message, response)
        else:
            if status_message:
                await status_message.edit(content=response)

        return response

    except LLMServiceError as e:
        print(f"[OPTIMIZED WORKFLOW] LLM service error: {e}")
        if status_message:
            if hasattr(e, 'retry_after') and e.retry_after:
                await status_message.edit(content=f"Sorry, the AI service is currently rate limited. Please try again later.")
            else:
                await status_message.edit(content="Sorry, the AI service is currently unavailable or overloaded. Please try again later.")
        raise
    except Exception as e:
        print(f"[OPTIMIZED WORKFLOW] Error: {e}")
        if status_message:
            await status_message.edit(content=f"Error processing your query: {str(e)}")
        return f"Error processing your query: {str(e)}"


# =============================================================================
# PLAYER ROASTING
# =============================================================================

async def roast_player(player_data, status_message=None):
    """
    Generate a humorous roast for a player based on their stats

    Args:
        player_data: The player data to roast
        status_message: Optional status message to update

    Returns:
        Formatted roast text or None if an error occurred
    """
    if not config.gemini_api_key:
        return "Sorry, the player roast feature is not available because the Gemini API key is not set."

    if not player_data or 'displayName' not in player_data:
        return None

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
    3. Savage comparisons are encouraged
    4. Mock any high KC's in easy bosses while pointing out zero KC's in real content
    5. Ridicule high levels in easy skills while roasting their terrible levels in actual challenging skills
    6. Use words like "pathetic", "embarrassing", "terrible", "laughable"
    7. End with a devastating final punch
    8. Sailing is a new skill in OSRS, it is already released.

    Player Name: {player_name}

    Player Stats:
    {player_context}

    Generate a single paragraph roast focusing on the player's noob-like stats or achievements.
    """

    try:
        print("[API CALL: LITELLM] player roast generation")
        prompt_tokens = count_tokens(prompt)
        print(f"  [TOKENS] Prompt: {prompt_tokens:,} tokens")
        print(f"  [TOKENS] Player context: {count_tokens(player_context):,} tokens")
        try:
            response = await llm_service.generate_text(prompt)
            response_tokens = count_tokens(response) if response else 0
            print(f"  [TOKENS] Response: {response_tokens:,} tokens")
            print(f"  [TOKENS] Total: {prompt_tokens + response_tokens:,} tokens")
            if response is None:
                return None
            response = response.strip()
            if not response:
                return None
        except LLMServiceError as e:
            # Update status message if available
            if status_message:
                if hasattr(e, 'retry_after') and e.retry_after:
                    await status_message.edit(content=f"Sorry, the AI service is currently rate limited. Please try again later.")
                else:
                    await status_message.edit(content="Sorry, the AI service is currently unavailable or overloaded. Please try again later.")
            # Re-raise to be handled by the command - this will exit the function immediately
            raise

        # Format the response for Discord
        formatted_response = f"**Roast of {player_name}**\n\n{response}"
        return formatted_response

    except Exception as e:
        if not isinstance(e, LLMServiceError):  # We already handle LLMServiceError above
            print(f"Error in model response: {e}")
        return None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def send_long_response(status_message, response, chunk_size=1900):
    """
    Sends a long response in Discord-friendly chunks, splitting at newlines if possible.
    The first chunk edits the status message, subsequent chunks are sent as new messages.
    """
    idx = 0
    length = len(response)
    pos = 0
    while pos < length:
        # Find the next chunk boundary
        if (length - pos) <= chunk_size:
            chunk = response[pos:]
            pos = length
        else:
            # Look for the last newline before chunk_size
            newline_pos = response.rfind('\n', pos, pos + chunk_size)
            if newline_pos == -1 or newline_pos == pos:
                # No newline found, or at the start, just split at chunk_size
                split_pos = pos + chunk_size
            else:
                split_pos = newline_pos + 1  # include the newline
            chunk = response[pos:split_pos]
            pos = split_pos
        # Add continuation marker if more content remains
        if pos < length:
            chunk = chunk.rstrip('\n') + "\n\n(Continued in next message)"
        if idx == 0:
            await status_message.edit(content=chunk)
        else:
            await status_message.channel.send(chunk)
        idx += 1


# =============================================================================


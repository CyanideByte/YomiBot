"""
Agentic Loop Implementation for YomiBot

This module implements an agentic loop that allows the LLM to iteratively
gather information by calling tools multiple times before generating a
final response. The agent tracks what has been queried, summarizes gathered
data between iterations, and signals when ready to respond.
"""

import asyncio
import json
import time
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from osrs.llm.llm_service import llm_service, LLMServiceError
from osrs.llm.identification_optimized import unified_identification
from osrs.llm.tools import AGENT_REQUEST_MORE_INFO_TOOL, AGENT_COMPLETE_TOOL
from osrs.wiseoldman import (
    fetch_player_details,
    get_guild_members_data,
    format_player_data
)
from osrs.wiki import fetch_osrs_wiki_pages
from osrs.llm.source_management import ensure_all_sources_included, clean_url_patterns


# Token counting
try:
    import tiktoken
    encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        """Count tokens in text using tiktoken."""
        if not text:
            return 0
        return len(encoding.encode(text))
except ImportError:
    def count_tokens(text: str) -> int:
        """Rough token count (1 token ≈ 4 chars)."""
        if not text:
            return 0
        return len(text) // 4


# Formatting rules (reused from query_processing)
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


@dataclass
class AgenticIteration:
    """Data class for tracking a single iteration of the agentic loop."""
    iteration_number: int
    wiki_pages_fetched: List[str] = field(default_factory=list)
    players_fetched: List[str] = field(default_factory=list)
    summary: str = ""
    content_tokens: int = 0


class AgenticLoop:
    """
    Manages the agentic loop for iterative information gathering.

    The agent loop works as follows:
    1. Initial identification using unified_identification()
    2. Loop (up to max_iterations):
       a. Present gathered information to LLM
       b. LLM calls agent_request_more_info() or agent_complete()
       c. If agent_request_more_info: fetch requested data, summarize, continue
       d. If agent_complete: break loop
    3. Generate final response with all gathered information
    """

    def __init__(
        self,
        user_query: str,
        guild_members: List[str],
        requester_name: str = None,
        status_message = None,
        max_iterations: int = 3
    ):
        """
        Initialize the agentic loop.

        Args:
            user_query: The user's query text
            guild_members: List of clan member names
            requester_name: Optional name of the user making the request
            status_message: Optional Discord message for status updates
            max_iterations: Maximum number of iterations (default: 3)
        """
        self.user_query = user_query
        self.guild_members = guild_members
        self.requester_name = requester_name or "Unknown"
        self.status_message = status_message
        self.max_iterations = max_iterations

        # State tracking
        self.current_iteration = 0
        self.queried_wiki_pages: Set[str] = set()
        self.queried_players: Set[str] = set()
        self.iterations: List[AgenticIteration] = []

        # Accumulated data
        self.all_wiki_content: str = ""
        self.all_player_data: List[Dict] = []
        self.wiki_sources: List[Dict] = []
        self.player_sources: List[Dict] = []

        # Guild members data for caching
        self.guild_members_data = get_guild_members_data()

    async def run(self) -> str:
        """
        Run the agentic loop and return the final response.

        Returns:
            The final response text
        """
        print("\n" + "=" * 70)
        print("[AGENTIC LOOP] Starting agentic loop")
        print("=" * 70)
        print(f"  Query: '{self.user_query[:100]}...'")
        print(f"  Max iterations: {self.max_iterations}")

        start_time = time.time()

        try:
            # Step 1: Initial identification
            await self._initial_identification()

            # Step 2: Iteration loop
            await self._iteration_loop()

            # Step 3: Generate final response
            response = await self._generate_final_response()

            total_time = time.time() - start_time
            print(f"\n[AGENTIC LOOP] Completed in {total_time:.2f}s")
            print(f"               Total iterations: {self.current_iteration}")
            print(f"               Wiki pages fetched: {len(self.queried_wiki_pages)}")
            print(f"               Players fetched: {len(self.queried_players)}")
            print("=" * 70)

            return response

        except LLMServiceError as e:
            if self.status_message:
                if hasattr(e, 'retry_after') and e.retry_after:
                    await self.status_message.edit(content="Sorry, the AI service is currently rate limited. Please try again later.")
                else:
                    await self.status_message.edit(content="Sorry, the AI service is currently unavailable or overloaded. Please try again later.")
            raise
        except Exception as e:
            print(f"[AGENTIC LOOP] Error: {e}")
            if self.status_message:
                await self.status_message.edit(content=f"Error processing your query: {str(e)}")
            return f"Error processing your query: {str(e)}"

    async def _initial_identification(self):
        """Step 1: Initial identification using unified_identification()."""
        print("\n[STEP 1] Initial Identification")

        if self.status_message:
            await self.status_message.edit(content="Analyzing query...")

        # Use unified_identification to get initial data
        result = await unified_identification(
            user_query=self.user_query,
            guild_members=self.guild_members,
            requester_name=self.requester_name
        )

        mentioned_players = result.get("mentioned_players", [])
        wiki_pages = result.get("wiki_pages", [])

        print(f"  Identified: {len(mentioned_players)} players, {len(wiki_pages)} wiki pages")

        # Fetch initial data
        if mentioned_players:
            await self._fetch_player_data(mentioned_players)

        if wiki_pages:
            await self._fetch_wiki_data(wiki_pages)

        # Create first iteration summary
        self.current_iteration = 1
        iteration = AgenticIteration(
            iteration_number=1,
            wiki_pages_fetched=list(wiki_pages),
            players_fetched=list(mentioned_players),
            summary=self._create_initial_summary()
        )
        self.iterations.append(iteration)

    async def _iteration_loop(self):
        """Step 2: Main iteration loop."""
        print("\n[STEP 2] Agentic Iteration Loop")

        while self.current_iteration < self.max_iterations:
            print(f"\n  [Iteration {self.current_iteration}/{self.max_iterations}]")

            # Build prompt for this iteration
            prompt = self._build_iteration_prompt()

            # Call LLM with agentic tools
            if self.status_message:
                await self.status_message.edit(
                    content=f"[Iteration {self.current_iteration}/{self.max_iterations}] Analyzing gathered information..."
                )

            print(f"    Calling LLM with agentic tools...")

            agentic_tools = [AGENT_REQUEST_MORE_INFO_TOOL, AGENT_COMPLETE_TOOL]
            result = await llm_service.generate_with_tools(
                prompt=prompt,
                tools=agentic_tools,
                tool_choice="auto"
            )

            # Process tool call
            tool_calls = result.get("tool_calls", [])

            if not tool_calls:
                print(f"    No tool calls - completing loop")
                break

            tool_call = tool_calls[0]
            function_name = tool_call["function"]["name"]
            args = json.loads(tool_call["function"]["arguments"])

            if function_name == "agent_request_more_info":
                # Continue gathering information
                success = await self._handle_request_more_info(args)

                if not success:
                    # No new information requested, complete
                    print(f"    No new info requested - completing loop")
                    break

                self.current_iteration += 1

            elif function_name == "agent_complete":
                # Agent is satisfied, complete the loop
                summary = args.get("summary", "No summary provided")
                print(f"    Agent complete: {summary}")
                break
            else:
                print(f"    Unexpected tool: {function_name}")
                break

        if self.current_iteration >= self.max_iterations:
            print(f"\n  Max iterations reached ({self.max_iterations})")

    async def _handle_request_more_info(self, args: Dict) -> bool:
        """
        Handle agent_request_more_info tool call.

        Args:
            args: Tool arguments (additional_wiki_pages, additional_players, reasoning)

        Returns:
            True if new information was requested, False otherwise
        """
        additional_wiki_pages = args.get("additional_wiki_pages", [])
        additional_players = args.get("additional_players", [])
        reasoning = args.get("reasoning", "")

        print(f"    Request: {reasoning}")
        print(f"    Wiki pages: {additional_wiki_pages}")
        print(f"    Players: {additional_players}")

        # Filter out already-queried items
        new_wiki_pages = [p for p in additional_wiki_pages if p not in self.queried_wiki_pages]
        new_players = [p for p in additional_players if p not in self.queried_players]

        if not new_wiki_pages and not new_players:
            print(f"    All requested info already fetched - nothing new")
            return False

        # Update status
        status_parts = []
        if new_wiki_pages:
            status_parts.append(f"Fetching {len(new_wiki_pages)} wiki page(s)")
        if new_players:
            status_parts.append(f"Fetching {len(new_players)} player(s)")

        if self.status_message:
            await self.status_message.edit(
                content=f"[Iteration {self.current_iteration + 1}/{self.max_iterations}] {', '.join(status_parts)}..."
            )

        # Fetch new data
        if new_wiki_pages:
            await self._fetch_wiki_data(new_wiki_pages)

        if new_players:
            await self._fetch_player_data(new_players)

        # Create iteration summary
        iteration = AgenticIteration(
            iteration_number=self.current_iteration + 1,
            wiki_pages_fetched=new_wiki_pages,
            players_fetched=new_players,
            summary=reasoning
        )
        self.iterations.append(iteration)

        return True

    async def _fetch_wiki_data(self, page_names: List[str]):
        """Fetch wiki page data."""
        print(f"    Fetching wiki pages: {page_names}")

        wiki_content, redirects, rejected_pages = await fetch_osrs_wiki_pages(page_names)

        for page in page_names:
            self.queried_wiki_pages.add(page)

        # Append to accumulated content
        if wiki_content:
            if self.all_wiki_content:
                self.all_wiki_content += "\n\n" + "="*50 + " NEW WIKI PAGES " + "="*50 + "\n\n"
            self.all_wiki_content += wiki_content

        # Build sources
        for page in page_names:
            normalized_page = page.replace(' ', '_')
            redirected_page = redirects.get(normalized_page, normalized_page)
            final_page_name = redirected_page.replace(' ', '_')

            if final_page_name not in rejected_pages:
                wiki_url = f"https://oldschool.runescape.wiki/w/{final_page_name}"
                if not any(s.get('url') == wiki_url for s in self.wiki_sources):
                    self.wiki_sources.append({
                        'type': 'wiki',
                        'name': final_page_name,
                        'url': wiki_url
                    })

        print(f"    Fetched {len(page_names)} wiki pages")

    async def _fetch_player_data(self, player_names: List[str]):
        """Fetch player data."""
        print(f"    Fetching player data: {player_names}")

        import aiohttp

        async with aiohttp.ClientSession() as session:
            tasks = []
            for player_name in player_names:
                # Find matching member data
                member_data = next(
                    (m['player'] for m in self.guild_members_data
                     if m['player']['displayName'].lower() == player_name.lower()),
                    None
                )
                if member_data and player_name not in self.queried_players:
                    tasks.append(fetch_player_details(member_data, session))

            if tasks:
                player_data_results = await asyncio.gather(*tasks)

                for player_name, player_data in zip(player_names, player_data_results):
                    if player_data:
                        self.queried_players.add(player_name)
                        self.all_player_data.append(player_data)
                        player_url = f"https://wiseoldman.net/players/{player_name.lower().replace(' ', '_')}"
                        if not any(s.get('url') == player_url for s in self.player_sources):
                            self.player_sources.append({
                                'type': 'wiseoldman',
                                'name': player_name,
                                'url': player_url
                            })

        print(f"    Fetched {len([p for p in player_names if p in self.queried_players])} player(s)")

    def _build_iteration_prompt(self) -> str:
        """Build the prompt for the current iteration."""
        # Build iteration summaries
        summaries_text = ""
        for iteration in self.iterations:
            summaries_text += f"\nIteration {iteration.iteration_number}:\n"
            summaries_text += f"  - Fetched: {', '.join(iteration.wiki_pages_fetched + iteration.players_fetched)}\n"
            if iteration.summary:
                summaries_text += f"  - Summary: {iteration.summary}\n"

        # Format player data
        player_context = ""
        if self.all_player_data:
            for player_data in self.all_player_data:
                formatted_data = format_player_data(player_data)
                if formatted_data:
                    player_name = player_data.get('displayName', 'Unknown')
                    player_context += f"\n===== {player_name} DATA =====\n"
                    player_context += formatted_data
                    player_context += "\n\n"

        # Build prompt
        prompt = f"""
You are an Old School RuneScape (OSRS) expert assistant using an agentic loop to gather information iteratively.

USER QUERY: {self.user_query}

INFORMATION GATHERED SO FAR:
{summaries_text}

"""

        if player_context:
            prompt += f"\nPLAYER DATA:\n{player_context}\n"

        if self.all_wiki_content:
            prompt += f"\nWIKI CONTENT:\n{self.all_wiki_content}\n"

        prompt += f"""
You have gathered information over {self.current_iteration} iteration(s).

IMPORTANT: You have access to TWO tools:
1. agent_request_more_info - Use this if you need MORE information to answer comprehensively
2. agent_complete - Use this when you have ENOUGH information to generate a great response

Guidelines:
- Only call agent_request_more_info if you genuinely need additional information that would SIGNIFICANTLY improve your answer
- Don't request more info for minor details - it's better to provide a great answer with what you have
- You can request up to 5 wiki pages and/or 5 players per iteration
- When satisfied, call agent_complete with a brief summary of what you gathered

Query context:
- Requester: {self.requester_name}
- Guild members available: {len(self.guild_members)}
- Wiki pages already fetched: {len(self.queried_wiki_pages)}
- Players already fetched: {len(self.queried_players)}

Remember: The goal is to provide a comprehensive answer to the user's question. Call agent_complete when you have enough information.
"""

        return prompt

    def _create_initial_summary(self) -> str:
        """Create a summary for the initial iteration."""
        parts = []
        if self.iterations and self.iterations[0].wiki_pages_fetched:
            parts.append(f"{len(self.iterations[0].wiki_pages_fetched)} wiki page(s)")
        if self.iterations and self.iterations[0].players_fetched:
            parts.append(f"{len(self.iterations[0].players_fetched)} player(s)")
        return "Initial data: " + ", ".join(parts) if parts else "No data fetched"

    async def _generate_final_response(self) -> str:
        """Step 3: Generate the final response."""
        print("\n[STEP 3] Generating Final Response")

        if self.status_message:
            await self.status_message.edit(content="Generating final response...")

        # Format player data
        player_context = ""
        valid_players = []
        if self.all_player_data:
            for player_data in self.all_player_data:
                formatted_data = format_player_data(player_data)
                if formatted_data:
                    player_name = player_data.get('displayName', 'Unknown')
                    player_context += f"\n===== {player_name} DATA =====\n"
                    player_context += formatted_data
                    player_context += "\n\n"
                    valid_players.append(player_data)

        # Build prompt
        prompt = f"""
You are an Old School RuneScape (OSRS) expert assistant. Your task is to answer the user's question using all the information you have gathered.

USER QUERY: {self.user_query}
"""

        if player_context:
            prompt += f"\nPLAYER DATA:\n{player_context}\n"

        if self.all_wiki_content:
            prompt += f"\nOSRS WIKI INFORMATION:\n{self.all_wiki_content}\n"

        prompt += f"""
INFORMATION GATHERING SUMMARY:
You performed {self.current_iteration} iteration(s) to gather this information.
"""

        for iteration in self.iterations:
            prompt += f"\nIteration {iteration.iteration_number}: "
            parts = iteration.wiki_pages_fetched + iteration.players_fetched
            prompt += ", ".join(parts) if parts else "No new data"

        prompt += f"""
{FORMATTING_RULES}
"""

        print(f"  Generating response...")
        print(f"  Prompt tokens: {count_tokens(prompt):,}")

        response = await llm_service.generate_text(prompt)

        print(f"  Response tokens: {count_tokens(response):,}")

        if not response:
            return "Error: Failed to generate response"

        response = response.strip()
        if not response:
            return "Error: Empty response generated"

        # Add sources
        valid_player_sources = [
            source for source in self.player_sources
            if any(p.get('displayName', '').lower() == source.get('name', '').lower() for p in valid_players)
        ]

        response = ensure_all_sources_included(
            response,
            valid_player_sources,
            self.wiki_sources,
            []  # No web sources in agentic loop yet
        )

        # Clean URLs
        for source in self.wiki_sources:
            url = source['url']
            clean_page = source['name'].replace(' ', '_')
            escaped_page = clean_page.replace('_', '\\_')
            escaped_url = f"https://oldschool.runescape.wiki/w/{escaped_page}"
            response = clean_url_patterns(response, url, escaped_url)

        for source in self.player_sources:
            url = source['url']
            response = clean_url_patterns(response, url)

        # Remove empty Sources sections
        response = re.sub(r'\n\nSources:\s*$', '', response.strip())

        return response


async def run_agentic_loop(
    user_query: str,
    guild_members: List[str],
    requester_name: str = None,
    status_message = None,
    max_iterations: int = 3
) -> str:
    """
    Convenience function to run the agentic loop.

    Args:
        user_query: The user's query text
        guild_members: List of clan member names
        requester_name: Optional name of the user making the request
        status_message: Optional Discord message for status updates
        max_iterations: Maximum number of iterations (default: 3)

    Returns:
        The final response text
    """
    loop = AgenticLoop(
        user_query=user_query,
        guild_members=guild_members,
        requester_name=requester_name,
        status_message=status_message,
        max_iterations=max_iterations
    )
    return await loop.run()

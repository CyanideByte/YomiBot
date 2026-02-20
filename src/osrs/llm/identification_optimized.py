"""
Optimized OSRS identification using unified parallel tool calling.

This module provides a single LLM call that identifies:
- Which clan members are mentioned
- Which wiki pages are relevant
- Which metrics are referenced (for clan-wide queries)
- What additional web searches are needed beyond the wiki

All in ONE parallel tool call instead of 4-5 separate calls.
"""

import asyncio
import json
import time
from typing import Dict, List, Tuple

from osrs.llm.llm_service import llm_service, LLMServiceError
from osrs.llm.tools import UNIFIED_IDENTIFICATION_TOOL

# Token counting (reuse from query_processing)
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


def log_tool_call(title: str, details: str = ""):
    """Print a formatted log message for tool calling."""
    print(f"[UNIFIED IDENTIFICATION] {title}")
    if details:
        print(f"                        {details}")


async def unified_identification(
    user_query: str,
    guild_members: List[str],
    image_urls: List[str] = None,
    requester_name: str = None
) -> Dict:
    """
    Single parallel LLM call that identifies everything needed for the query.

    This replaces 4-5 separate LLM calls with one parallel call.

    Args:
        user_query: The user's query text
        guild_members: List of clan member names
        image_urls: Optional list of image URLs to analyze
        requester_name: Optional name of the user making the request

    Returns:
        {
            "player_scope": str,  # "all_members" | "no_members" | "specific_members"
            "mentioned_players": list,
            "wiki_pages": list,
            "metrics": list,
            "needs_web_search": bool,
            "is_prohibited": bool
        }
    """
    start_time = time.time()

    log_tool_call("START", f"Query: '{user_query[:100]}...'")
    log_tool_call("CONFIG", f"Guild members: {len(guild_members)}, Requester: {requester_name or 'None'}")

    # Build the prompt
    members_list = str(guild_members)

    prompt = f"""
You are an OSRS bot assistant analyzing a user query. You need to identify what information is needed to answer the query.

CLAN MEMBERS: {members_list}
REQUESTER NAME: {requester_name or 'Unknown'}

USER QUERY: {user_query}

{"IMAGE CONTEXT: User has attached images that may contain OSRS items." if image_urls else ""}

IMPORTANT ABBREVIATIONS:
- cox = chambers_of_xeric
- cm = chambers_of_xeric_challenge_mode
- tob = theatre_of_blood
- hm tob / hard tob = theatre_of_blood_hard_mode
- toa = tombs_of_amascut
- expert toa = tombs_of_amascut_expert
- quiver / colosseum = sol_heredit (boss KC - killing Sol Heredit guarantees a quiver)
- infernal cape / inferno = tzkal_zuk

SCOPE RULES (CRITICAL):
1. "Who has X" or "clan total for X" or similar clan-wide queries? Leave mentioned_players EMPTY and populate metrics with the boss/metric (e.g., ["sol_heredit"] for "who has a quiver")
2. Specific players named? List them in mentioned_players (max 10), leave metrics EMPTY (player data includes all stats)
3. Wiki-only (no players, no clan stats)? Leave both mentioned_players and metrics EMPTY

Analyze this query and use the unified_identification function now.
"""

    try:
        log_tool_call("LLM CALL", "Calling model with unified_identification tool...")

        result = await llm_service.generate_with_tools(
            prompt=prompt,
            tools=[UNIFIED_IDENTIFICATION_TOOL],
            tool_choice="required"
        )

        # Log token usage
        prompt_tokens = count_tokens(prompt)
        print(f"  [TOKENS] Identification prompt: {prompt_tokens:,} tokens")
        # Note: we don't have access to response tokens here for tool calls

        # Check for tool calls
        if not result.get("tool_calls"):
            log_tool_call("ERROR", "No tool calls returned!")
            return _get_default_response()

        tool_call = result["tool_calls"][0]
        function_name = tool_call["function"]["name"]

        if function_name != "unified_identification":
            log_tool_call("ERROR", f"Unexpected tool called: {function_name}")
            return _get_default_response()

        # Parse the arguments
        args = json.loads(tool_call["function"]["arguments"])

        elapsed = time.time() - start_time

        # Determine scope from data (simplified - no more player_scope enum)
        mentioned_players = args.get("mentioned_players", [])
        metrics = args.get("metrics", [])

        # Derive player_scope:
        # - mentioned_players non-empty = specific_members
        # - mentioned_players empty + metrics populated = all_members
        # - both empty = no_members
        if mentioned_players:
            player_scope = "specific_members"
        elif metrics:
            player_scope = "all_members"
        else:
            player_scope = "no_members"

        # Log the results
        log_tool_call("SUCCESS", f"Completed in {elapsed:.2f}s")
        log_tool_call("RESULTS", "")
        print(f"                        - Player scope: {player_scope} (derived)")
        print(f"                        - Players: {mentioned_players}")
        print(f"                        - Wiki pages: {args.get('wiki_pages', [])}")
        print(f"                        - Metrics: {metrics}")
        print(f"                        - Search queries: {args.get('search_queries', [])}")

        return {
            "player_scope": player_scope,  # Derived, not from tool
            "mentioned_players": mentioned_players,
            "wiki_pages": args.get("wiki_pages", []),
            "metrics": metrics,
            "search_queries": args.get("search_queries", []),
            "elapsed_time": elapsed  # Add timing info
        }

    except LLMServiceError as e:
        log_tool_call("ERROR", f"LLM service error: {e}")
        raise
    except json.JSONDecodeError as e:
        log_tool_call("ERROR", f"JSON decode error: {e}")
        return _get_default_response()
    except Exception as e:
        log_tool_call("ERROR", f"Unexpected error: {e}")
        return _get_default_response()


def _get_default_response() -> Dict:
    """Return default safe values when identification fails."""
    log_tool_call("FALLBACK", "Using default safe values")
    return {
        "player_scope": "no_members",  # Derived from empty lists
        "mentioned_players": [],
        "wiki_pages": [],
        "metrics": [],
        "search_queries": []
    }


# Convenience wrapper for backward compatibility
async def identify_and_fetch_all_optimized(
    user_query: str,
    guild_members: List[str],
    requester_name: str = None,
    status_message = None
) -> Tuple[List, List, bool, List, bool, float]:
    """
    Optimized version that combines multiple identification steps.

    Replaces:
    - identify_and_fetch_players
    - identify_and_fetch_wiki_pages (identification part)
    - identify_and_fetch_metrics (identification part)
    - is_player_only_query
    - is_wiki_only_query

    Returns:
        (player_names, wiki_pages, is_all_members, metrics, search_queries, elapsed_time)
    """
    result = await unified_identification(
        user_query=user_query,
        guild_members=guild_members,
        requester_name=requester_name
    )

    # Map to expected return format
    player_names = []
    is_all_members = False

    if result["player_scope"] == "all_members":
        is_all_members = True
    elif result["player_scope"] == "specific_members":
        player_names = result["mentioned_players"]

    return (
        player_names,
        result["wiki_pages"],
        is_all_members,
        result["metrics"],
        result["search_queries"],
        result.get("elapsed_time", 0.0)
    )

"""
OSRS Wiki and Player Identification using Tool Calling

This module uses LLM tool/function calling instead of string parsing
to identify wiki pages, players, metrics, and classify queries.

Works with both local models (LM Studio) and cloud models (Gemini, etc.)
"""

import asyncio
import json
from osrs.llm.llm_service import llm_service, LLMServiceError
from osrs.llm.tools import (
    IDENTIFY_WIKI_PAGES_TOOL,
    IDENTIFY_PLAYERS_TOOL,
    CLASSIFY_QUERY_TOOL,
    IDENTIFY_METRICS_TOOL,
    SUGGEST_FOLLOWUP_WIKI_PAGES_TOOL,
    GENERATE_SEARCH_TERM_TOOL
)


async def identify_wiki_pages(user_query: str, image_urls: list[str] = None) -> list:
    """
    Use LLM tool calling to identify relevant wiki pages for the query.

    Args:
        user_query: The user's query text
        image_urls: Optional list of image URLs to analyze

    Returns:
        List of wiki page names (with underscores)
    """
    prompt = f"""
    You are an assistant that helps determine which Old School RuneScape (OSRS) wiki pages to fetch based on user queries.

    Query: {user_query}

    Identify relevant wiki pages using the identify_wiki_pages function.
    """

    if image_urls:
        prompt += f"\n\nImage URLs provided: {', '.join(image_urls)}"

    try:
        print("[API CALL: LLM WITH TOOLS] identify_wiki_pages")
        result = await llm_service.generate_with_tools(
            prompt=prompt,
            tools=[IDENTIFY_WIKI_PAGES_TOOL],
            tool_choice="required"  # Force tool call
        )

        # Extract tool calls
        if result["tool_calls"]:
            for tc in result["tool_calls"]:
                if tc["function"]["name"] == "identify_wiki_pages":
                    args = json.loads(tc["function"]["arguments"])
                    page_names = args.get("page_names", [])
                    print(f"Identified wiki pages: {page_names}")
                    return page_names

        # Fallback: empty list
        print("No wiki pages identified")
        return []

    except LLMServiceError:
        raise
    except Exception as e:
        print(f"Error identifying wiki pages: {e}")
        return []


async def identify_mentioned_players(
    user_query: str,
    guild_members: list,
    requester_name: str = None
) -> tuple[list, bool]:
    """
    Use LLM tool calling to identify mentioned players in the query.

    Args:
        user_query: The user's query text
        guild_members: List of clan member names
        requester_name: Optional name of the user making the request

    Returns:
        tuple: (list of mentioned players, bool indicating if query refers to all members)
    """
    members_list = str(guild_members)

    prompt = f"""
    Clan member list:
    {members_list}

    Based on the above member list, analyze the user query and identify which clan members are mentioned or referenced.

    User query: {user_query}

    Requester name: {requester_name or 'Unknown'}

    Use the identify_players function to classify the query scope and identify specific members if applicable.
    """

    try:
        print("[API CALL: LLM WITH TOOLS] identify_mentioned_players")
        result = await llm_service.generate_with_tools(
            prompt=prompt,
            tools=[IDENTIFY_PLAYERS_TOOL],
            tool_choice="required"
        )

        if result["tool_calls"]:
            for tc in result["tool_calls"]:
                if tc["function"]["name"] == "identify_players":
                    args = json.loads(tc["function"]["arguments"])
                    scope = args.get("scope")
                    player_names = args.get("player_names", [])

                    if scope == "all_members":
                        print("Query refers to all clan members")
                        return [], True
                    elif scope == "no_members":
                        print("No members identified in query")
                        return [], False
                    else:  # specific_members
                        print(f"Identified specific members: {player_names}")
                        return player_names[:10], False

        return [], False

    except LLMServiceError:
        raise
    except Exception as e:
        print(f"Error identifying mentioned members: {e}")
        return [], False


async def classify_query(
    user_query: str,
    player_data_list: list = None,
    wiki_content: str = None
) -> dict:
    """
    Use LLM tool calling to classify the query and determine what information is needed.

    Replaces: is_player_only_query, is_prohibited_query, is_wiki_only_query

    Args:
        user_query: The user's query text
        player_data_list: Optional list of player data objects
        wiki_content: Optional wiki page content

    Returns:
        dict with keys:
            - is_prohibited: bool
            - is_player_only: bool
            - is_wiki_sufficient: bool (only if wiki_content provided)
            - needs_web_search: bool
    """
    prompt = f"""
    Analyze this query about OSRS and classify it.

    Query: "{user_query}"
    """

    if player_data_list:
        simplified_data = []
        for player_data in player_data_list:
            player_name = player_data.get('displayName', 'Unknown')
            simplified_data.append({
                'name': player_name,
                'data_available': 'skills and boss kill counts'
            })
        prompt += f"\n\nAvailable player data: {simplified_data}"

    if wiki_content:
        prompt += f"\n\nWiki content available (first 1000 chars): {wiki_content[:1000]}..."

    prompt += """
    Use the classify_query function to determine:
    1. Whether the query is about prohibited topics (RWT, botting, unofficial clients, private servers)
    2. Whether it can be answered with only player data
    3. Whether a web search is needed
    """

    try:
        print("[API CALL: LLM WITH TOOLS] classify_query")
        result = await llm_service.generate_with_tools(
            prompt=prompt,
            tools=[CLASSIFY_QUERY_TOOL],
            tool_choice="required"
        )

        if result["tool_calls"]:
            for tc in result["tool_calls"]:
                if tc["function"]["name"] == "classify_query":
                    args = json.loads(tc["function"]["arguments"])
                    print(f"Query classification: {args}")
                    return args

        # Default fallback
        return {
            "is_prohibited": False,
            "is_player_only": False,
            "needs_web_search": True
        }

    except LLMServiceError:
        raise
    except Exception as e:
        print(f"Error classifying query: {e}")
        return {
            "is_prohibited": False,
            "is_player_only": False,
            "needs_web_search": True
        }


async def identify_mentioned_metrics(user_query: str) -> list:
    """
    Use LLM tool calling to identify mentioned metrics in the query.

    Args:
        user_query: The user's query text

    Returns:
        List of identified metric names
    """
    prompt = f"""
    Identify which OSRS metrics (skills, bosses, activities) are mentioned or implied in this query.

    User query: "{user_query}"

    Use the identify_metrics function to return the metrics.
    """

    try:
        print("[API CALL: LLM WITH TOOLS] identify_mentioned_metrics")
        result = await llm_service.generate_with_tools(
            prompt=prompt,
            tools=[IDENTIFY_METRICS_TOOL],
            tool_choice="required"
        )

        if result["tool_calls"]:
            for tc in result["tool_calls"]:
                if tc["function"]["name"] == "identify_metrics":
                    args = json.loads(tc["function"]["arguments"])
                    metrics = args.get("metrics", [])
                    print(f"Identified metrics: {metrics}")
                    return metrics

        return []

    except LLMServiceError:
        raise
    except Exception as e:
        print(f"Error identifying mentioned metrics: {e}")
        return []


async def suggest_followup_wiki_pages(
    user_query: str,
    full_response: str,
    wiki_pages_already_identified: list[str]
) -> list[str]:
    """
    Use LLM tool calling to suggest additional wiki pages.

    Args:
        user_query: The original user query
        full_response: The previously generated response
        wiki_pages_already_identified: List of already identified page names

    Returns:
        List of additional wiki page names to fetch
    """
    already_identified_str = ", ".join(wiki_pages_already_identified) if wiki_pages_already_identified else "None"

    prompt = f"""
    You are an assistant that helps determine if any ADDITIONAL Old School RuneScape (OSRS) wiki pages should be fetched to fill in gaps in knowledge or to verify information.

    User Query: {user_query}

    Previous Response: {full_response}

    Wiki pages already identified: {already_identified_str}

    Use the suggest_followup_wiki_pages function to recommend additional pages.
    """

    try:
        print("[API CALL: LLM WITH TOOLS] suggest_followup_wiki_pages")
        result = await llm_service.generate_with_tools(
            prompt=prompt,
            tools=[SUGGEST_FOLLOWUP_WIKI_PAGES_TOOL],
            tool_choice="required"
        )

        if result["tool_calls"]:
            for tc in result["tool_calls"]:
                if tc["function"]["name"] == "suggest_followup_wiki_pages":
                    args = json.loads(tc["function"]["arguments"])
                    pages = args.get("additional_pages", [])
                    print(f"Additional wiki pages: {pages}")
                    return pages

        return []

    except LLMServiceError:
        raise
    except Exception as e:
        print(f"Error suggesting followup wiki pages: {e}")
        return []


async def generate_search_term(query: str) -> str:
    """
    Use LLM tool calling to generate a search term or determine if no search is needed.

    Args:
        query: The user's query text

    Returns:
        Search term string, or None if no search needed
    """
    prompt = f"""
    Given the following user query, determine if additional information is needed to provide a complete answer.

    User Query: {query}

    Use the generate_search_term function to either provide a search term or indicate no search is needed.
    """

    try:
        print("[API CALL: LLM WITH TOOLS] generate_search_term")
        result = await llm_service.generate_with_tools(
            prompt=prompt,
            tools=[GENERATE_SEARCH_TERM_TOOL],
            tool_choice="required"
        )

        if result["tool_calls"]:
            for tc in result["tool_calls"]:
                if tc["function"]["name"] == "generate_search_term":
                    args = json.loads(tc["function"]["arguments"])
                    if args.get("search_needed"):
                        term = args.get("search_term")
                        print(f"Generated search term: {term}")
                        return term
                    else:
                        print("No search needed")
                        return None

        return None

    except LLMServiceError:
        raise
    except Exception as e:
        print(f"Error generating search term: {e}")
        return None


# Convenience wrappers that maintain backward compatibility with original functions

async def is_player_only_query(user_query: str, player_data_list: list) -> bool:
    """Wrapper for backward compatibility"""
    result = await classify_query(user_query, player_data_list=player_data_list)
    return result.get("is_player_only", False)


async def is_prohibited_query(user_query: str) -> bool:
    """Wrapper for backward compatibility"""
    result = await classify_query(user_query)
    return result.get("is_prohibited", False)


async def is_wiki_only_query(user_query: str, wiki_content: str) -> bool:
    """Wrapper for backward compatibility"""
    result = await classify_query(user_query, wiki_content=wiki_content)
    # If wiki is sufficient, no web search is needed
    return not result.get("needs_web_search", True)

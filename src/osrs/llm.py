# This file now serves as a re-export module for backward compatibility
# The actual implementation has been refactored into separate modules

# Configure the Gemini API
import google.generativeai as genai
from config.config import config

# Import wiki-related functions from wiki.py
from osrs.wiki import fetch_osrs_wiki_pages, fetch_osrs_wiki

# Import web search functions from search.py
from osrs.search import get_web_search_context, format_search_results

# Import player tracking functions from tracker.py
from osrs.wiseoldman import get_guild_members, fetch_player_details, format_player_data

# Import from refactored modules
from osrs.llm.commands import register_commands
from osrs.llm.query_processing import process_unified_query, roast_player, UNIFIED_SYSTEM_PROMPT, user_interactions, INTERACTION_WINDOW
from osrs.llm.identification import (
    identify_wiki_pages, 
    identify_mentioned_players, 
    generate_search_term,
    is_player_only_query,
    identify_and_fetch_players,
    identify_and_fetch_wiki_pages
)
from osrs.llm.image_processing import fetch_image, identify_items_in_images
from osrs.llm.source_management import (
    collect_source_urls,
    build_sources_section,
    ensure_all_sources_included,
    clean_url_patterns
)

# Configure the Gemini API
if config.gemini_api_key:
    genai.configure(api_key=config.gemini_api_key)
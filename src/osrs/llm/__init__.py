# Re-export necessary functions for backward compatibility
from osrs.llm.commands import register_commands
from osrs.llm.query_processing import process_unified_query, roast_player
from osrs.llm.identification import generate_search_term
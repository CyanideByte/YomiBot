"""
Tool definitions for OSRS LLM function calling.

All tools use OpenAI-compatible format, which works with both:
- Cloud models (Gemini, OpenAI, Anthropic, etc.) via litellm
- Local models (LM Studio, Ollama, etc.) via litellm
"""

# Available metrics for OSRS
SKILL_METRICS = [
    'overall', 'attack', 'defence', 'strength', 'hitpoints', 'ranged', 'prayer', 'magic',
    'cooking', 'woodcutting', 'fletching', 'fishing', 'firemaking', 'crafting', 'smithing',
    'mining', 'herblore', 'agility', 'thieving', 'slayer', 'farming', 'runecrafting',
    'hunter', 'construction', 'sailing'
]

ACTIVITY_METRICS = [
    'league_points', 'bounty_hunter_hunter', 'bounty_hunter_rogue', 'clue_scrolls_all',
    'clue_scrolls_beginner', 'clue_scrolls_easy', 'clue_scrolls_medium', 'clue_scrolls_hard',
    'clue_scrolls_elite', 'clue_scrolls_master', 'last_man_standing', 'pvp_arena',
    'soul_wars_zeal', 'guardians_of_the_rift', 'colosseum_glory', 'collections_logged'
]

BOSS_METRICS = [
    'abyssal_sire', 'alchemical_hydra', 'amoxliatl', 'araxxor', 'artio', 'barrows_chests',
    'bryophyta', 'callisto', 'calvarion', 'cerberus', 'chambers_of_xeric',
    'chambers_of_xeric_challenge_mode', 'chaos_elemental', 'chaos_fanatic', 'commander_zilyana',
    'corporeal_beast', 'crazy_archaeologist', 'dagannoth_prime', 'dagannoth_rex',
    'dagannoth_supreme', 'deranged_archaeologist', 'duke_sucellus', 'general_graardor',
    'giant_mole', 'grotesque_guardians', 'hespori', 'kalphite_queen', 'king_black_dragon',
    'kraken', 'kreearra', 'kril_tsutsaroth', 'lunar_chests', 'mimic', 'nex', 'nightmare',
    'phosanis_nightmare', 'obor', 'phantom_muspah', 'sarachnis', 'scorpia', 'scurrius',
    'skotizo', 'sol_heredit', 'spindel', 'tempoross', 'the_gauntlet', 'the_corrupted_gauntlet',
    'the_hueycoatl', 'the_leviathan', 'the_royal_titans', 'the_whisperer', 'theatre_of_blood',
    'theatre_of_blood_hard_mode', 'thermonuclear_smoke_devil', 'tombs_of_amascut',
    'tombs_of_amascut_expert', 'tzkal_zuk', 'tztok_jad', 'vardorvis', 'venenatis', 'vetion',
    'vorkath', 'wintertodt', 'zalcano', 'zulrah'
]

ALL_METRICS = SKILL_METRICS + ACTIVITY_METRICS + BOSS_METRICS


# Tool: Identify wiki pages
IDENTIFY_WIKI_PAGES_TOOL = {
    "type": "function",
    "function": {
        "name": "identify_wiki_pages",
        "description": "Identify which OSRS wiki pages are relevant to the user's query based on explicitly mentioned items, NPCs, bosses, skills, or concepts. Maximum 10 pages. Use underscores instead of spaces (e.g., Dragon_scimitar, Abyssal_demon). For items, use exact names. For NPCs/bosses, include their Strategies page if available. For skills, include their Training page. When referring to Chambers of Xeric/CoX, include Ancient_chest. When referring to Theatre of Blood/ToB, include Monumental_chest. When referring to Tombs of Amascut/ToA, include Chest_(Tombs_of_Amascut). If no relevant pages are found, return an empty array.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_names": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "pattern": "^[A-Za-z0-9_()]{1,40}$"
                    },
                    "description": "List of wiki page names using underscores (e.g., Dragon_scimitar). Empty array if no pages found.",
                    "maxItems": 10
                }
            },
            "required": ["page_names"]
        }
    }
}

# Tool: Identify players
IDENTIFY_PLAYERS_TOOL = {
    "type": "function",
    "function": {
        "name": "identify_players",
        "description": "Identify which clan members are mentioned or referenced in the query. Returns the scope (all_members, no_members, or specific_members) and optionally a list of specific player names. If the user asks about themself (I/me/my), include the requester_name in the specific_members list. Limit specific_members to 10 names maximum.",
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["all_members", "no_members", "specific_members"],
                    "description": "Whether query refers to all clan members, no members, or specific members"
                },
                "player_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of specific clan member names mentioned (max 10). Only included when scope is 'specific_members'.",
                    "maxItems": 10
                }
            },
            "required": ["scope"]
        }
    }
}

# Tool: Classify query
CLASSIFY_QUERY_TOOL = {
    "type": "function",
    "function": {
        "name": "classify_query",
        "description": "Classify the query to determine what information sources are needed and whether it's about prohibited topics. Prohibited topics include: real world trading (buying/selling gold, accounts, services), botting and bot clients, unofficial 3rd party clients, private servers (RSPS). Also determines if the query can be answered with only player data, and if a web search is needed beyond wiki content.",
        "parameters": {
            "type": "object",
            "properties": {
                "is_prohibited": {
                    "type": "boolean",
                    "description": "Whether the query is about prohibited topics"
                },
                "is_player_only": {
                    "type": "boolean",
                    "description": "Whether the query can be answered using only player stats/boss KCs without wiki info"
                },
                "needs_web_search": {
                    "type": "boolean",
                    "description": "Whether a web search is needed for additional information beyond wiki"
                }
            },
            "required": ["is_prohibited", "is_player_only", "needs_web_search"]
        }
    }
}

# Tool: Identify metrics
IDENTIFY_METRICS_TOOL = {
    "type": "function",
    "function": {
        "name": "identify_metrics",
        "description": "Identify which OSRS metrics (skills, bosses, activities) are mentioned or implied in the query. Common abbreviations: cox=chambers_of_xeric, tob=theatre_of_blood, toa=tombs_of_amascut, cm/chambers_of_xeric_cm=chambers_of_xeric_challenge_mode, hm tob/hard tob=theatre_of_blood_hard_mode, expert toa=tombs_of_amascut_expert, infernal cape=tzkal_zuk, quiver/colosseum=sol_heredit. Sailing is a released skill. Return the exact metric names in lowercase with underscores.",
        "parameters": {
            "type": "object",
            "properties": {
                "metrics": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ALL_METRICS
                    },
                    "description": "List of identified metrics in lowercase with underscores"
                }
            },
            "required": ["metrics"]
        }
    }
}

# Tool: Suggest followup wiki pages
SUGGEST_FOLLOWUP_WIKI_PAGES_TOOL = {
    "type": "function",
    "function": {
        "name": "suggest_followup_wiki_pages",
        "description": "Suggest additional OSRS wiki pages to fill knowledge gaps or verify uncertain information based on the user query and previous response. Exclude pages already provided. Maximum 5 pages. Return empty array if no additional pages are needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "additional_pages": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "pattern": "^[A-Za-z0-9_()]{1,40}$"
                    },
                    "description": "List of additional wiki page names to fetch (max 5). Empty array if no additional pages needed.",
                    "maxItems": 5
                }
            },
            "required": ["additional_pages"]
        }
    }
}

# Tool: Generate search term
GENERATE_SEARCH_TERM_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_search_term",
        "description": "Generate an effective search term if additional information is needed to answer the query, or indicate no search is needed. The search term should be 2-5 words focused on OSRS content.",
        "parameters": {
            "type": "object",
            "properties": {
                "search_needed": {
                    "type": "boolean",
                    "description": "Whether a web search is needed"
                },
                "search_term": {
                    "type": "string",
                    "description": "The search term to use (2-5 words). Only included if search_needed is true.",
                    "maxLength": 100
                }
            },
            "required": ["search_needed"]
        }
    }
}

# Tool: Unified Identification (OPTIMIZED - combines multiple tools into one parallel call)
UNIFIED_IDENTIFICATION_TOOL = {
    "type": "function",
    "function": {
        "name": "unified_identification",
        "description": "Comprehensive query analysis that identifies all needed information in parallel. Analyzes the query to determine: which clan members are mentioned (list their names), which wiki pages are relevant, which OSRS metrics to fetch for the entire clan, and what additional web searches are needed beyond the wiki.\n\nIMPORTANT ABBREVIATIONS: cox=chambers_of_xeric, cm=chambers_of_xeric_challenge_mode, tob=theatre_of_blood, hm tob/hard tob=theatre_of_blood_hard_mode, toa=tombs_of_amascut, expert toa=tombs_of_amascut_expert, quiver/colosseum=sol_heredit (boss KC), infernal cape=tzkal_zuk. Sailing is a released skill.\n\nSCOPE RULES:\n1) Specific players mentioned? List their names in mentioned_players (max 10). Player data fetch includes ALL their stats, so leave metrics empty.\n2) Clan-wide query asking 'who has X' or 'clan total for X'? Leave mentioned_players EMPTY and populate metrics to fetch clan-wide stats for that boss/metric.\n3) Wiki-only (no players at all)? Leave both mentioned_players and metrics empty.\n\nFor search_queries: only include if wiki pages aren't enough to answer the query (e.g., recent updates, niche topics, current prices).",
        "parameters": {
            "type": "object",
            "properties": {
                "mentioned_players": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of specific clan member names mentioned (max 10). Include requester_name if user asks about themselves (I/me/my). Leave EMPTY for clan-wide queries or wiki-only queries.",
                    "maxItems": 10
                },
                "wiki_pages": {
                    "type": "array",
                    "items": {"type": "string", "pattern": "^[A-Za-z0-9_()]{1,40}$"},
                    "description": "List of relevant OSRS wiki page names using underscores (e.g., Dragon_scimitar, Abyssal_demon). Maximum 10 pages.",
                    "maxItems": 10
                },
                "metrics": {
                    "type": "array",
                    "items": {"type": "string", "enum": ALL_METRICS},
                    "description": "List of metrics to fetch for the ENTIRE CLAN (clan-wide stats). Only populate when no specific players are mentioned and clan-wide stats are needed (e.g., 'who has X' queries). Use exact metric names: cox=chambers_of_xeric, cm=chambers_of_xeric_challenge_mode, tob=theatre_of_blood, hm tob=theatre_of_blood_hard_mode, toa=tombs_of_amascut, expert toa=tombs_of_amascut_expert, quiver/colosseum=sol_heredit (boss KC), infernal cape=tzkal_zuk. Leave EMPTY for specific player queries (their data includes all stats) and wiki-only queries."
                },
                "search_queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of web search queries to run for additional information beyond the wiki pages (max 3). Each query should be 2-5 words focused on OSRS content. Leave EMPTY if wiki pages are sufficient to answer the query.",
                    "maxItems": 3
                }
            },
            "required": ["mentioned_players", "wiki_pages", "metrics", "search_queries"]
        }
    }
}


# All tools combined
ALL_TOOLS = [
    IDENTIFY_WIKI_PAGES_TOOL,
    IDENTIFY_PLAYERS_TOOL,
    CLASSIFY_QUERY_TOOL,
    IDENTIFY_METRICS_TOOL,
    SUGGEST_FOLLOWUP_WIKI_PAGES_TOOL,
    GENERATE_SEARCH_TERM_TOOL,
    UNIFIED_IDENTIFICATION_TOOL,  # New optimized tool
]


def get_tools_for_workflow(tools_needed: list[str] = None) -> list:
    """
    Get a subset of tools based on workflow needs.

    Args:
        tools_needed: List of tool names to include. If None, returns all tools.

    Returns:
        List of tool definitions
    """
    if tools_needed is None:
        return ALL_TOOLS

    tool_map = {
        "identify_wiki_pages": IDENTIFY_WIKI_PAGES_TOOL,
        "identify_players": IDENTIFY_PLAYERS_TOOL,
        "classify_query": CLASSIFY_QUERY_TOOL,
        "identify_metrics": IDENTIFY_METRICS_TOOL,
        "suggest_followup_wiki_pages": SUGGEST_FOLLOWUP_WIKI_PAGES_TOOL,
        "generate_search_term": GENERATE_SEARCH_TERM_TOOL,
    }

    return [tool_map[name] for name in tools_needed if name in tool_map]

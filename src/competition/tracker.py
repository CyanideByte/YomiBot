import requests
from utils.helpers import transform_metric_name

# Replace with your clan's group ID
GROUP_ID = "3773"
BASE_URL = "https://api.wiseoldman.net/v2/groups"

# List of OSRS skills
SKILLS = [
    "attack", "strength", "defence", "ranged", "prayer", "magic", "runecrafting",
    "construction", "hitpoints", "agility", "herblore", "thieving", "crafting",
    "fletching", "slayer", "hunter", "mining", "smithing", "fishing", "cooking",
    "firemaking", "woodcutting", "farming"
]

def get_recent_competitions(group_id):
    """
    Retrieves the most recent competitions for the group, 
    sorted by start date (most recent first).
    """
    url = f"{BASE_URL}/{group_id}/competitions"
    try:
        response = requests.get(url)
        response.raise_for_status()
        competitions = response.json()
        competitions.sort(key=lambda x: x["startsAt"], reverse=True)
        return competitions
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return []

# Register competition commands
def setup_competition_commands(bot):
    @bot.command(name='sotw', help='Displays the most recent Skill of the Week competitions.')
    async def sotw(ctx):
        """Command to print Skill Metrics (Skill of the Week)."""
        recent_competitions = get_recent_competitions(GROUP_ID)
        if not recent_competitions:
            await ctx.send("No recent competitions found or an error occurred.")
            return

        # Filter and gather the 6 most recent skill competitions
        skill_competitions = [
            comp for comp in recent_competitions if comp['metric'].lower() in SKILLS
        ][:6]

        if not skill_competitions:
            await ctx.send("No recent skill competitions found.")
            return

        # Transform the metric names for display
        skill_metrics = [transform_metric_name(comp['metric']) for comp in skill_competitions]
        await ctx.send(f"Last six skills: {', '.join(skill_metrics)}")

    @bot.command(name='botw', help='Displays the most recent Boss of the Week competitions.')
    async def botw(ctx):
        """Command to print Boss Metrics (Boss of the Week)."""
        recent_competitions = get_recent_competitions(GROUP_ID)
        if not recent_competitions:
            await ctx.send("No recent competitions found or an error occurred.")
            return

        # Filter and gather the 6 most recent boss competitions
        boss_competitions = [
            comp for comp in recent_competitions if comp['metric'].lower() not in SKILLS
        ][:6]

        if not boss_competitions:
            await ctx.send("No recent boss competitions found.")
            return

        # Transform the metric names for display
        boss_metrics = [transform_metric_name(comp['metric']) for comp in boss_competitions]
        await ctx.send(f"Last six bosses: {', '.join(boss_metrics)}")
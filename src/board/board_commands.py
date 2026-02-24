import discord
from discord.ext import commands
from typing import TYPE_CHECKING
import io
import os
from pathlib import Path

import PIL.Image
import PIL.ImageDraw
from PIL import ImageFont

from .board_manager import board_manager, Tile, Team

if TYPE_CHECKING:
    pass

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
BOARD_IMAGE_FILE = PROJECT_ROOT / 'board' / 'board.png'

# Board layout coordinates (from original board.py)
START_X, START_Y = 85, 1015
H_SPACING, V_SPACING = 165, 163
cols = [START_X + (i * H_SPACING) for i in range(9)]
rows = [START_Y, START_Y - V_SPACING, START_Y - (V_SPACING*2), START_Y - (V_SPACING*3), START_Y - (V_SPACING*4), 130]
coords = [(cols[0], rows[0]), (cols[0], rows[1]), (cols[0], rows[2]), (cols[0], rows[3]), (cols[0], rows[4]), (cols[1], rows[4]), (cols[2], rows[4]), (cols[2], rows[3]), (cols[2], rows[2]), (cols[2], rows[1]), (cols[2], rows[0]), (cols[3], rows[0]), (cols[4], rows[0]), (cols[4], rows[1]), (cols[4], rows[2]), (cols[4], rows[3]), (cols[4], rows[4]), (cols[5], rows[4]), (cols[6], rows[4]), (cols[6], rows[3]), (cols[6], rows[2]), (cols[6], rows[1]), (cols[7], rows[1]), (cols[8], rows[1]), (cols[8], rows[2]), (cols[8], rows[3]), (cols[8], rows[4]), (cols[8], rows[5])]


def generate_board_image() -> io.BytesIO:
    """Generate the board image with current team positions and leaderboard.
    
    Returns:
        io.BytesIO: A bytes buffer containing the PNG image
    """
    # Load the base board image
    if not BOARD_IMAGE_FILE.exists():
        raise FileNotFoundError(f"Board template image not found: {BOARD_IMAGE_FILE}")
    
    img = PIL.Image.open(BOARD_IMAGE_FILE).convert("RGB")
    draw = PIL.ImageDraw.Draw(img)
    
    # Load fonts with fallback for Linux systems
    try:
        TEAM_FONT = ImageFont.truetype("arial.ttf", 24)
        HDR_FONT = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        # Try common Linux font paths
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ]
        TEAM_FONT = None
        for font_path in font_paths:
            try:
                TEAM_FONT = ImageFont.truetype(font_path, 24)
                HDR_FONT = ImageFont.truetype(font_path, 22)
                break
            except OSError:
                continue
        if TEAM_FONT is None:
            # Final fallback to default font
            TEAM_FONT = ImageFont.load_default()
            HDR_FONT = ImageFont.load_default()
    
    # Group teams by position for dogpiles (use tile_index for array access)
    assignments = {}
    for team in board_manager.teams:
        idx = team.tile_index
        if idx not in assignments: assignments[idx] = []
        assignments[idx].append(team)
    
    # 1. DRAW TEAM STACKS
    for pos_idx, teams_on_tile in assignments.items():
        x, y = coords[pos_idx]
        # Push names down toward bottom of tile (moved 10px upward)
        safe_bottom = y + 15
        for j, team in enumerate(reversed(teams_on_tile)):
            curr_y = safe_bottom - (j * 30)
            # Trim team name to max 25 characters
            display_name = team.name[:25] if len(team.name) > 25 else team.name
            bbox = draw.textbbox((x, curr_y), display_name, font=TEAM_FONT, anchor="mm")
            
            # Calculate pillbox bounds with padding
            pill_left = bbox[0] - 16
            pill_right = bbox[2] + 16
            pill_top = bbox[1] - 5
            pill_bottom = bbox[3] + 5
            
            # Cap pillbox to image bounds
            pill_left = max(0, pill_left)
            pill_right = min(img.width, pill_right)
            
            # Calculate luminance to determine text color for contrast
            luminance = 0.299 * team.color[0] + 0.587 * team.color[1] + 0.114 * team.color[2]
            txt_color = "black" if luminance > 128 else "white"
            
            draw.rounded_rectangle([pill_left, pill_top, pill_right, pill_bottom], radius=8, fill=team.color, outline="black", width=2)
            
            # Adjust text position if pillbox was capped
            text_x = x
            if pill_left == 0:
                # Left tile: left-align text within the capped pillbox
                text_x = pill_left + (pill_right - pill_left) // 2
            elif pill_right == img.width:
                # Right tile: right-align text within the capped pillbox
                text_x = pill_left + (pill_right - pill_left) // 2
            
            draw.text((text_x, curr_y), display_name, fill=txt_color, font=TEAM_FONT, anchor="mm")
    
    # 2. DRAW LEADERBOARD
    LB_W, LB_H = 750, 185  # Extended width for team names and tile info
    # Position leaderboard near right edge of image (only 10px margin)
    LB_X, LB_Y = img.width - LB_W - 10, img.height - LB_H - 5
    draw.rectangle([LB_X, LB_Y, LB_X + LB_W, LB_Y + LB_H], fill=(20, 15, 10), outline=(210, 160, 40), width=2)
    draw.text((LB_X + LB_W/2, LB_Y + 15), "LEADERBOARD", fill=(210, 160, 40), font=HDR_FONT, anchor="mm")
    
    # RR header above reroll column - moved right for team name space
    draw.text((LB_X + 400, LB_Y + 38), "RR", fill=(150, 140, 120), font=HDR_FONT, anchor="mm")
    
    # Sort teams by position (highest first), limit to top 5 for display
    sorted_leaderboard = sorted(board_manager.teams, key=lambda t: t.position, reverse=True)[:5]
    
    for rank, team in enumerate(sorted_leaderboard, 1):
        row_y = LB_Y + 45 + (rank * 24)
        draw.rectangle([LB_X + 15, row_y - 7, LB_X + 25, row_y + 7], fill=team.color, outline="white")
        # Trim team name to max 25 characters for leaderboard display
        lb_name = team.name[:25] if len(team.name) > 25 else team.name
        draw.text((LB_X + 35, row_y), f"{rank}. {lb_name}", fill="white", font=TEAM_FONT, anchor="lm")
        
        # Reroll count - moved right for team name space
        rr_color = (0, 255, 0) if team.rerolls > 0 else (255, 0, 0)
        draw.text((LB_X + 400, row_y), str(team.rerolls), fill=rr_color, font=TEAM_FONT, anchor="mm")
        
        # Tile info from the Tile object (use tile_index for array access) - moved further right
        current_tile = board_manager.tiles[team.tile_index]
        draw.text((LB_X + 480, row_y), f"Tile {current_tile.number}: {current_tile.name}", fill=(180, 170, 150), font=TEAM_FONT, anchor="lm")
    
    # Save to bytes buffer
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer


def setup_board_commands(bot: commands.Bot):
    """Set up board-related commands for the bot"""
    
    def resolve_team(team_ref: str) -> tuple:
        """Resolve a team reference (ID or name) to a Team object.
        
        Args:
            team_ref: Either a numeric team ID or a team name (case-insensitive)
            
        Returns:
            Tuple of (Team object or None, error_message or None)
        """
        # Try parsing as numeric ID first
        if team_ref.isdigit():
            team = board_manager.get_team(int(team_ref))
            if team:
                return team, None
            return None, f"No team found with ID `{team_ref}`"
        
        # Try looking up by name (case-insensitive)
        team = board_manager.get_team_by_name(team_ref)
        if team:
            return team, None
        
        # Not found - provide helpful message
        return None, f"No team found with name or ID `{team_ref}`. Use `!teams` to see all team IDs."
    
    async def resolve_player_names(ctx, discord_ids: list, saved_names: list) -> list:
        """Resolve player display names from Discord, falling back to saved names.
        
        Args:
            ctx: Discord context for guild lookup
            discord_ids: List of Discord user IDs (strings)
            saved_names: List of saved display names from JSON
            
        Returns:
            List of display names (server nickname if found, else saved name)
        """
        resolved_names = []
        for i, discord_id in enumerate(discord_ids):
            saved_name = saved_names[i] if i < len(saved_names) else f"Player {i+1}"
            try:
                # Try to get the member from the guild (for server nickname)
                member = ctx.guild.get_member(int(discord_id))
                if member:
                    # Use display_name which prioritizes server nickname over global name
                    resolved_names.append(member.display_name)
                else:
                    # Fallback to fetching user globally if not in guild
                    user = await bot.fetch_user(int(discord_id))
                    if user:
                        resolved_names.append(user.display_name)
                    else:
                        resolved_names.append(saved_name)
            except Exception:
                # If lookup fails, use saved name
                resolved_names.append(saved_name)
        return resolved_names
    
    @bot.command(name='board', help='Display the current bingo board with team positions')
    async def board_command(ctx):
        """Display the current bingo board state as an image"""
        if not board_manager.is_loaded():
            await ctx.reply("Board state has not been loaded. Please check the configuration.")
            return
        
        try:
            # Generate the board image
            image_buffer = generate_board_image()
            
            # Create discord file attachment
            file = discord.File(image_buffer, filename='bingo_board.png')
            
            # Send the image
            await ctx.reply(file=file)
            
        except FileNotFoundError as e:
            await ctx.reply(f"Error: Board template image not found.")
            print(f"Board image error: {e}")
        except Exception as e:
            await ctx.reply("An error occurred while generating the board image.")
            print(f"Board generation error: {e}")
    
    @bot.command(name='tiles', help='List all tiles on the board')
    async def tiles_command(ctx):
        """List all tiles on the bingo board"""
        if not board_manager.is_loaded():
            await ctx.reply("Board state has not been loaded.")
            return
        
        tiles_list = []
        for tile in board_manager.tiles:
            reroll_marker = " 🎲" if tile.gives_reroll else ""
            tiles_list.append(f"**{tile.number}.** {tile.name}{reroll_marker}")
        
        # Split into chunks to avoid message length limits
        chunks = []
        current_chunk = []
        current_length = 0
        
        for tile_str in tiles_list:
            if current_length + len(tile_str) > 1900:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_length = 0
            current_chunk.append(tile_str)
            current_length += len(tile_str)
        
        if current_chunk:
            chunks.append("\n".join(current_chunk))
        
        for i, chunk in enumerate(chunks):
            if len(chunks) > 1:
                await ctx.reply(f"**Tiles (Page {i+1}/{len(chunks)}):**\n{chunk}")
            else:
                await ctx.reply(f"**Tiles:**\n{chunk}")
    
    @bot.command(name='teams', help='List all teams and their positions')
    async def teams_command(ctx):
        """List all teams and their current positions"""
        if not board_manager.is_loaded():
            await ctx.reply("Board state has not been loaded.")
            return
        
        if not board_manager.teams:
            await ctx.reply("No teams are registered.")
            return
        
        lines = ["**Teams:**"]
        for team in board_manager.teams:
            tile = board_manager.get_tile(team.position)
            tile_name = f"Tile {tile.number}: {tile.name}" if tile else "Unknown"
            # Resolve current display names from Discord
            player_names = await resolve_player_names(ctx, team.discord_ids, team.players)
            players = ", ".join(player_names) if player_names else "No players"
            lines.append(
                f"• **{team.name}** (ID: {team.team_id})\n"
                f"  Position: {tile_name} | Rerolls: {team.rerolls} | Players: {players}\n"
            )
        
        await ctx.reply("\n".join(lines))
    
    @bot.command(name='team', help='Get info about a specific team. Usage: !team [team_id_or_name]')
    async def team_command(ctx, *, team_ref: str = None):
        """Get information about a specific team by ID or name, or your own team if no ID provided."""
        if not board_manager.is_loaded():
            await ctx.reply("Board state has not been loaded.")
            return
        
        # If no team_ref provided, try to get user's team
        if team_ref is None:
            team = board_manager.get_team_by_discord_id(str(ctx.author.id))
            if not team:
                await ctx.reply(f"❌ {ctx.author.display_name}, you are not registered to any team! Use `!team <team_id_or_name>` to view a specific team.")
                return
        else:
            # Strip quotes from team_ref
            team_ref = team_ref.strip('"\'')
            team, error_msg = resolve_team(team_ref)
            if not team:
                await ctx.reply(f"❌ {error_msg}")
                return
        
        tile = board_manager.get_tile(team.position)
        tile_name = f"Tile {tile.number}: {tile.name}" if tile else "Unknown"
        # Resolve current display names from Discord
        player_names = await resolve_player_names(ctx, team.discord_ids, team.players)
        players = "\n  • ".join(player_names) if player_names else "No players"
        
        reroll_status = f"🎲 {team.rerolls} reroll(s) available" if team.rerolls > 0 else "❌ No rerolls"
        
        message = (
            f"**{team.name}** (ID: {team.team_id})\n"
            f"📍 Position: {tile_name}\n"
            f"{reroll_status}\n"
            f"👥 Players:\n  • {players}"
        )
        
        await ctx.reply(message)
    
    @bot.command(name='status', help='Show your team\'s current status')
    async def status_command(ctx):
        """Show the current status of the team you belong to."""
        if not board_manager.is_loaded():
            await ctx.reply("❌ Board state has not been loaded.")
            return
        
        # Get user's team
        team = board_manager.get_team_by_discord_id(str(ctx.author.id))
        if not team:
            await ctx.reply(f"❌ {ctx.author.display_name}, you are not registered to any team!")
            return
        
        tile = board_manager.get_tile(team.position)
        tile_name = f"Tile {tile.number}: {tile.name}" if tile else "Unknown"
        # Resolve current display names from Discord
        player_names = await resolve_player_names(ctx, team.discord_ids, team.players)
        players = "\n  • ".join(player_names) if player_names else "No players"
        
        reroll_status = f"🎲 {team.rerolls} reroll(s) available" if team.rerolls > 0 else "❌ No rerolls"
        completion_status = "✅ Tile completed - ready to roll!" if team.tile_completed else "⏳ Complete current tile before rolling"
        
        message = (
            f"**{team.name}** (ID: {team.team_id})\n"
            f"📍 Position: {tile_name}\n"
            f"{reroll_status}\n"
            f"📊 {completion_status}\n"
            f"👥 Players:\n  • {players}"
        )
        
        await ctx.reply(message)
    
    @bot.command(name='registerteam', help='Register or update a team. Usage: !registerteam [team_id] [team_name] @user1 @user2 ...')
    @commands.has_role('Mod')
    async def registerteam_command(ctx, *, args: str = ""):
        """Register or update a team with Discord user mentions.
        
        Usage: !registerteam [team_id] [team_name] @user1 @user2 ...
        
        If team_id is not provided, the next available ID will be assigned.
        
        Examples:
            !registerteam @Alice @Bob
            !registerteam 1 @Alice @Bob
            !registerteam 2 "Alpha Squad" @Charlie @Dave
            !registerteam "Alpha Squad" @Charlie @Dave
        """
        if not board_manager.is_loaded():
            await ctx.reply("Board state has not been loaded.")
            return
        
        mentions = ctx.message.mentions
        
        if not mentions:
            await ctx.reply("Please mention at least one Discord user to add to the team.\n"
                          "Usage: `!registerteam [team_id] [team_name] @user1 @user2 ...`")
            return
        
        # Parse args to extract team_id (if numeric) and team_name
        team_id = None
        team_name = None
        
        if args:
            # Remove all mentions from args to get the remaining content
            content = args.strip()
            for mention in mentions:
                content = content.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
            content = content.strip()
            
            # Check if first word is a number (team_id)
            words = content.split()
            if words and words[0].isdigit():
                team_id = int(words[0])
                # Rest could be team name
                remaining = " ".join(words[1:]).strip()
                if remaining:
                    # Remove quotes if present
                    if remaining.startswith('"') and remaining.endswith('"'):
                        remaining = remaining[1:-1]
                    if remaining.startswith("'") and remaining.endswith("'"):
                        remaining = remaining[1:-1]
                    if remaining:
                        team_name = remaining
            else:
                # No team_id provided, content is team name
                if content:
                    # Remove quotes if present
                    if content.startswith('"') and content.endswith('"'):
                        content = content[1:-1]
                    if content.startswith("'") and content.endswith("'"):
                        content = content[1:-1]
                    if content:
                        team_name = content
        
        # If no team_id provided, find next available
        if team_id is None:
            existing_ids = {t.team_id for t in board_manager.teams}
            team_id = 1
            while team_id in existing_ids:
                team_id += 1
        
        # Get Discord IDs and display names
        discord_ids = [str(user.id) for user in mentions]
        player_names = [user.display_name for user in mentions]
        
        # Check if this is an update or new registration
        existing_team = board_manager.get_team(team_id)
        
        # If updating and no name provided, keep the existing name
        if existing_team and team_name is None:
            team_name = existing_team.name
        
        print(f"[Board] {'Updating' if existing_team else 'Registering'} team {team_id}: {team_name or f'Team {team_id}'} with players: {player_names}")
        
        # Register the team
        success = board_manager.register_team(
            team_id=team_id,
            discord_ids=discord_ids,
            player_names=player_names,
            name=team_name
        )
        
        if success:
            team = board_manager.get_team(team_id)
            players_str = ", ".join(player_names)
            print(f"[Board] Successfully {'updated' if existing_team else 'registered'} team {team_id}")
            if existing_team:
                await ctx.reply(f"✅ Updated **{team.name}** (ID: {team_id})\n"
                              f"👥 Players: {players_str}")
            else:
                await ctx.reply(f"✅ Registered **{team.name}** (ID: {team_id})\n"
                              f"👥 Players: {players_str}")
        else:
            print(f"[Board] Failed to {'update' if existing_team else 'register'} team {team_id}")
            await ctx.reply("❌ Failed to register team. Please check the logs.")
    
    @bot.command(name='deleteteam', help='Delete a team by ID or name. Usage: !deleteteam <team_id_or_name>')
    @commands.has_role('Mod')
    async def deleteteam_command(ctx, *, team_ref: str = None):
        """Delete a team by its ID or name."""
        if not board_manager.is_loaded():
            await ctx.reply("Board state has not been loaded.")
            return
        
        # Validate arguments
        if team_ref is None:
            await ctx.reply(
                "❌ **Usage:** `!deleteteam <team_id_or_name>`\n"
                "Deletes a team from the board.\n\n"
                "**Examples:**\n"
                "• `!deleteteam 1` - Delete team ID 1\n"
                "• `!deleteteam Natural Born Winners` - Delete team by name\n\n"
                "💡 Use `!teams` to see all team IDs and names."
            )
            return
        
        # Strip quotes from team_ref
        team_ref = team_ref.strip('"\'')
        team, error_msg = resolve_team(team_ref)
        if not team:
            await ctx.reply(f"❌ {error_msg}")
            return
        
        team_id = team.team_id
        
        team_name = team.name
        print(f"[Board] Deleting team {team_id} ({team_name})")
        success = board_manager.delete_team(team_id)
        
        if success:
            print(f"[Board] Successfully deleted team {team_id}")
            await ctx.reply(f"✅ Deleted team **{team_name}** (ID: {team_id})")
        else:
            print(f"[Board] Failed to delete team {team_id}")
            await ctx.reply("❌ Failed to delete team. Please check the logs.")
    
    @bot.command(name='reloadbingo', help='Reload board state from JSON file')
    @commands.has_role('Mod')
    async def reloadbingo_command(ctx):
        """Reload the board state from the JSON file."""
        print("[Board] Reloading board state from JSON file...")
        success = board_manager.load_state()
        
        if success:
            print(f"[Board] Successfully reloaded board state: {len(board_manager.tiles)} tiles, {len(board_manager.teams)} teams")
            await ctx.reply(f"✅ Reloaded board state: {len(board_manager.tiles)} tiles, {len(board_manager.teams)} teams")
        else:
            print("[Board] Failed to reload board state")
            await ctx.reply("❌ Failed to reload board state. Please check the logs.")
    
    @bot.command(name='complete', help='Mark your team\'s current tile as completed')
    async def complete_command(ctx):
        """Mark your team's current tile as completed, enabling !roll."""
        if not board_manager.is_loaded():
            await ctx.reply("❌ Board state has not been loaded.")
            return
        
        # Check if user is part of a team
        team = board_manager.get_team_by_discord_id(str(ctx.author.id))
        if not team:
            await ctx.reply(f"❌ {ctx.author.display_name}, you are not registered to any team!")
            return
        
        if team.tile_completed:
            await ctx.reply(f"⚠️ **{team.name}** has already marked their current tile as complete. Use `!roll` to advance!")
            return
        
        current_tile = board_manager.tiles[team.tile_index]
        team.tile_completed = True
        
        # Check if this tile grants a reroll bonus on completion
        if current_tile.gives_reroll:
            team.rerolls += 1
            reroll_msg = f"\n🎲 **Bonus!** This tile grants a reroll! ({team.rerolls} reroll(s) now)"
        else:
            reroll_msg = ""
        
        # Check if this is the final tile
        is_final_tile = team.position >= len(board_manager.tiles)
        
        board_manager.save_state()
        
        print(f"[Board] {team.name} marked tile {current_tile.number} as complete")
        
        if is_final_tile:
            # Big congratulations message for completing the final tile!
            await ctx.reply(
                f"🎉🎊🏆 **CONGRATULATIONS!** 🏆🎊🎉\n"
                f"**{team.name}** has completed the **FINAL TILE**!\n"
                f"Tile {current_tile.number}: {current_tile.name}{reroll_msg}\n\n"
                f"🌟 They have finished the bingo board! 🌟"
            )
        else:
            await ctx.reply(
                f"✅ **{team.name}** has completed **Tile {current_tile.number}: {current_tile.name}**!{reroll_msg}\n"
                f"🎲 Use `!roll` to advance to the next tile."
            )
    
    @bot.command(name='reroll', help='Use a reroll point to roll again from your last completed position')
    async def reroll_command(ctx):
        """Use a reroll point to roll again from the last completed tile position."""
        import random
        
        if not board_manager.is_loaded():
            await ctx.reply("❌ Board state has not been loaded.")
            return
        
        # Check if user is part of a team
        team = board_manager.get_team_by_discord_id(str(ctx.author.id))
        if not team:
            await ctx.reply(f"❌ {ctx.author.display_name}, you are not registered to any team!")
            return
        
        # If tile is already completed, they should use !roll instead
        if team.tile_completed:
            await ctx.reply(f"✅ **{team.name}** has already completed their current tile! Use `!roll` to advance normally.")
            return
        
        # Check if team has reroll points
        if team.rerolls <= 0:
            await ctx.reply(f"❌ **{team.name}** has no reroll points available!")
            return
        
        # Check if team is already at the final tile
        if team.position >= len(board_manager.tiles):
            await ctx.reply(f"🏆 **{team.name}** has already reached the final tile!")
            return
        
        # Use a reroll point
        team.rerolls -= 1
        
        # Roll the die (1-6) from the last completed position (1-based)
        # Ensure the result is different from the last roll
        result = random.randint(1, 6)
        while result == team.last_roll:
            result = random.randint(1, 6)
        team.last_roll = result  # Store the new roll result
        base_position = team.last_completed_position
        new_position = min(base_position + result, len(board_manager.tiles))
        
        # Update team state
        old_position = team.position
        team.position = new_position
        # tile_completed stays False since they used a reroll
        
        new_tile = board_manager.tiles[new_position - 1]  # Convert to 0-based index
        
        board_manager.save_state()
        
        print(f"[Board] {team.name} used reroll, rolled {result}, moved from tile {old_position} to {new_position} (base: {base_position})")
        
        await ctx.reply(
            f"🔄 **{team.name}** used a reroll point!\n"
            f"🎲 Rolled a **{result}** from Tile {base_position}!\n"
            f"📍 Moved to **Tile {new_tile.number}: {new_tile.name}**\n"
            f"🎲 **{team.rerolls}** reroll(s) remaining.\n"
            f"✅ Use `!complete` when you've finished this tile."
        )
    
    @bot.command(name='settile', aliases=['tileset'], help='Move a team to a specific tile. Usage: !settile <team_id_or_name> <tile_number>')
    @commands.has_role('Mod')
    async def settile_command(ctx, *, args: str = ""):
        """Move a team to a specific tile (Mod only)."""
        if not board_manager.is_loaded():
            await ctx.reply("❌ Board state has not been loaded.")
            return
        
        # Parse arguments - last word should be tile number, rest is team reference
        args = args.strip()
        if not args:
            await ctx.reply(
                "❌ **Usage:** `!settile <team_id_or_name> <tile_number>`\n"
                "Moves a team to a specific tile.\n\n"
                "**Examples:**\n"
                "• `!settile 1 5` - Move team ID 1 to tile 5\n"
                "• `!settile Natural Born Winners 17` - Move team by name\n\n"
                "💡 Use `!teams` to see all team IDs and names."
            )
            return
        
        # Split args and find the tile number (last numeric argument)
        words = args.split()
        tile_number = None
        team_ref = None
        
        # Try to find a number at the end
        for i in range(len(words) - 1, -1, -1):
            if words[i].isdigit():
                tile_number = int(words[i])
                team_ref = " ".join(words[:i]).strip()
                break
        
        if not tile_number or not team_ref:
            await ctx.reply(
                "❌ **Usage:** `!settile <team_id_or_name> <tile_number>`\n"
                "Could not parse command. Make sure to provide a team and tile number.\n\n"
                "**Examples:**\n"
                "• `!settile 1 5` - Move team ID 1 to tile 5\n"
                "• `!settile Natural Born Winners 17` - Move team by name\n\n"
                "💡 Use `!teams` to see all team IDs and names."
            )
            return
        
        # Remove quotes from team_ref if present
        team_ref = team_ref.strip('"\'')
        
        team, error_msg = resolve_team(team_ref)
        if not team:
            await ctx.reply(f"❌ {error_msg}")
            return
        
        # tile_number is now 1-based (matching JSON and display)
        if tile_number < 1 or tile_number > len(board_manager.tiles):
            await ctx.reply(f"❌ Invalid tile number. Must be between 1 and {len(board_manager.tiles)}.")
            return
        
        old_position = team.position
        old_tile = board_manager.tiles[old_position - 1] if 1 <= old_position <= len(board_manager.tiles) else None
        new_tile = board_manager.tiles[tile_number - 1]
        
        team.position = tile_number  # Now 1-based
        team.tile_completed = False  # Team needs to complete this tile before rolling
        board_manager.save_state()
        
        print(f"[Board] Mod moved {team.name} from tile {old_position} to tile {tile_number}")
        
        await ctx.reply(
            f"✅ Moved **{team.name}** from Tile {old_position} to **Tile {new_tile.number}: {new_tile.name}**\n"
            f"📍 Team must complete this tile before rolling."
        )
    
    @bot.command(name='setreroll', aliases=['setrerolls'], help='Set reroll count for a team. Usage: !setreroll <team_id_or_name> <count>')
    @commands.has_role('Mod')
    async def setreroll_command(ctx, *, args: str = ""):
        """Set the number of rerolls for a team (Mod only)."""
        if not board_manager.is_loaded():
            await ctx.reply("❌ Board state has not been loaded.")
            return
        
        # Parse arguments - last word should be count, rest is team reference
        args = args.strip()
        if not args:
            await ctx.reply(
                "❌ **Usage:** `!setreroll <team_id_or_name> <count>`\n"
                "Sets the number of rerolls for a team.\n\n"
                "**Examples:**\n"
                "• `!setreroll 1 3` - Set team ID 1's rerolls to 3\n"
                "• `!setreroll Natural Born Winners 2` - Set team by name\n\n"
                "💡 Use `!teams` to see all team IDs and names."
            )
            return
        
        # Split args and find the count (last numeric argument)
        words = args.split()
        count = None
        team_ref = None
        
        # Try to find a number at the end
        for i in range(len(words) - 1, -1, -1):
            if words[i].isdigit():
                count = int(words[i])
                team_ref = " ".join(words[:i]).strip()
                break
        
        if count is None or not team_ref:
            await ctx.reply(
                "❌ **Usage:** `!setreroll <team_id_or_name> <count>`\n"
                "Could not parse command. Make sure to provide a team and count.\n\n"
                "**Examples:**\n"
                "• `!setreroll 1 3` - Set team ID 1's rerolls to 3\n"
                "• `!setreroll Natural Born Winners 2` - Set team by name\n\n"
                "💡 Use `!teams` to see all team IDs and names."
            )
            return
        
        # Remove quotes from team_ref if present
        team_ref = team_ref.strip('"\'')
        
        team, error_msg = resolve_team(team_ref)
        if not team:
            await ctx.reply(f"❌ {error_msg}")
            return
        
        if count < 0:
            await ctx.reply("❌ Reroll count cannot be negative.")
            return
        
        old_count = team.rerolls
        team.rerolls = count
        board_manager.save_state()
        
        print(f"[Board] Mod set {team.name} rerolls from {old_count} to {count}")
        
        await ctx.reply(f"✅ Set **{team.name}**'s rerolls to **{count}** (was {old_count}).")
    
    @bot.command(name='roll', help='Roll to advance on the bingo board')
    async def roll_command(ctx):
        """Roll to advance your team on the bingo board."""
        import random
        
        if not board_manager.is_loaded():
            await ctx.reply("❌ Board state has not been loaded.")
            return
        
        # Check if user is part of a team
        team = board_manager.get_team_by_discord_id(str(ctx.author.id))
        if not team:
            await ctx.reply(f"❌ {ctx.author.display_name}, you are not registered to any team!")
            return
        
        # Check if team has completed their current tile
        if not team.tile_completed:
            if team.rerolls > 0:
                await ctx.reply(f"❌ **{team.name}** has not completed their current tile yet! Use `!complete` when done, or use `!reroll` to roll again from your last completed tile (you have **{team.rerolls}** reroll(s) available).")
            else:
                await ctx.reply(f"❌ **{team.name}** has not completed their current tile yet! Use `!complete` when done.")
            return
        
        # Check if team is already at the final tile
        if team.position >= len(board_manager.tiles):
            await ctx.reply(f"🏆 **{team.name}** has already reached the final tile!")
            return
        
        # Save the current position as last_completed before rolling
        team.last_completed_position = team.position
        
        # Roll the die (1-6) - positions are 1-based
        result = random.randint(1, 6)
        team.last_roll = result  # Store the roll result for reroll prevention
        new_position = min(team.position + result, len(board_manager.tiles))
        
        # Update team state
        old_position = team.position
        team.position = new_position
        team.tile_completed = False  # Must complete new tile before next roll
        
        new_tile = board_manager.tiles[new_position - 1]  # Convert to 0-based index
        
        board_manager.save_state()
        
        print(f"[Board] {team.name} rolled {result}, moved from tile {old_position} to {new_position}")
        
        await ctx.reply(
            f"🎲 **{ctx.author.display_name}** of **{team.name}** rolled a **{result}**!\n"
            f"📍 Moved from Tile {old_position} to **Tile {new_tile.number}: {new_tile.name}**\n"
            f"✅ Use `!complete` when you've finished this tile."
        )
    
    @bot.command(name='changename', help='Change your team\'s name. Usage: !changename [team_id_or_name] <new_name>')
    async def changename_command(ctx, *, args: str = ""):
        """Change the name of a team.
        
        Team members can change their own team's name.
        Mods can change any team's name by specifying the team_id_or_name.
        
        If team_id_or_name is not provided, uses the team the user belongs to.
        """
        if not board_manager.is_loaded():
            await ctx.reply("❌ Board state has not been loaded.")
            return
        
        if not args:
            await ctx.reply(
                "❌ **Usage:** `!changename [team_id_or_name] <new_name>`\n"
                "Changes a team's name.\n\n"
                "**Examples:**\n"
                "• `!changename New Team Name` - Change your own team's name\n"
                "• `!changename 1 Alpha Squad` - Change team ID 1's name\n"
                "• `!changename \"Old Name\" \"New Name\"` - Change team by name (quotes optional)\n\n"
                "💡 Use `!teams` to see all team IDs and names."
            )
            return
        
        # Check if user is a Mod
        is_mod = any(role.name == 'Mod' for role in ctx.author.roles)
        user_id = str(ctx.author.id)
        
        # Strip quotes from the entire args first
        args = args.strip()
        
        # Try to find a team reference at the start
        # We need to try matching team names from the start of the args
        team_ref = None
        new_name = None
        found_team = None
        
        # Try progressively longer prefixes to find a team match
        words = args.split()
        for i in range(len(words), 0, -1):
            potential_ref = " ".join(words[:i]).strip('"\'')
            team, _ = resolve_team(potential_ref)
            if team:
                found_team = team
                team_ref = potential_ref
                new_name = " ".join(words[i:]).strip('"\'')
                break
        
        if not found_team:
            # No team reference found, treat entire args as new name for user's team
            found_team = board_manager.get_team_by_discord_id(user_id)
            if not found_team:
                await ctx.reply(f"❌ {ctx.author.display_name}, you are not registered to any team!")
                return
            new_name = args.strip('"\'')
        else:
            # Check if the user is a member of this team (Mods can bypass)
            if not is_mod and user_id not in found_team.discord_ids:
                await ctx.reply(f"❌ {ctx.author.display_name}, you are not a member of **{found_team.name}**!")
                return
        
        # Validate new name
        if not new_name:
            await ctx.reply("❌ Please provide a new name. Usage: `!changename [team_id_or_name] <new_name>`")
            return
        
        # Validate name length
        if len(new_name) > 25:
            await ctx.reply("❌ Team name cannot exceed 25 characters.")
            return
        
        if len(new_name.strip()) == 0:
            await ctx.reply("❌ Team name cannot be empty.")
            return
        
        old_name = found_team.name
        found_team.name = new_name.strip()
        board_manager.save_state()
        
        print(f"[Board] {ctx.author.display_name} changed team {found_team.team_id} name from '{old_name}' to '{found_team.name}'")
        
        await ctx.reply(f"✅ Changed team name from **{old_name}** to **{found_team.name}**!")
    
    @bot.command(name='updateroster', help='Update team members without changing name. Usage: !updateroster <team_id_or_name> @user1 @user2 ...')
    @commands.has_role('Mod')
    async def updateroster_command(ctx, *, args: str = ""):
        """Update team members without changing the team name (Mod only)."""
        if not board_manager.is_loaded():
            await ctx.reply("❌ Board state has not been loaded.")
            return
        
        mentions = ctx.message.mentions
        
        if not mentions:
            await ctx.reply(
                "❌ **Usage:** `!updateroster <team_id_or_name> @user1 @user2 ...`\n"
                "Updates team members without changing the team name.\n\n"
                "**Examples:**\n"
                "• `!updateroster 1 @Alice @Bob` - Update team ID 1's roster\n"
                "• `!updateroster Natural Born Winners @Alice @Bob` - Update team by name\n\n"
                "💡 Use `!teams` to see all team IDs and names."
            )
            return
        
        # Remove mentions from args to get team reference
        content = args
        for mention in mentions:
            content = content.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
        team_ref = content.strip().strip('"\'')
        
        if not team_ref:
            await ctx.reply(
                "❌ **Usage:** `!updateroster <team_id_or_name> @user1 @user2 ...`\n"
                "Please provide a team ID or name.\n\n"
                "💡 Use `!teams` to see all team IDs and names."
            )
            return
        
        team, error_msg = resolve_team(team_ref)
        if not team:
            await ctx.reply(f"❌ {error_msg}")
            return
        
        team_id = team.team_id
        
        # Get Discord IDs and display names
        discord_ids = [str(user.id) for user in mentions]
        player_names = [user.display_name for user in mentions]
        
        old_name = team.name
        
        # Update the team (this will remove players from other teams automatically)
        success = board_manager.register_team(
            team_id=team_id,
            discord_ids=discord_ids,
            player_names=player_names,
            name=old_name  # Keep existing name
        )
        
        if success:
            players_str = ", ".join(player_names)
            print(f"[Board] Updated roster for team {team_id}: {players_str}")
            await ctx.reply(f"✅ Updated **{team.name}** (ID: {team_id}) roster\n"
                          f"👥 Players: {players_str}")
        else:
            await ctx.reply("❌ Failed to update team roster. Please check the logs.")

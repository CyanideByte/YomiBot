import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import threading

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
BOARD_STATE_FILE = PROJECT_ROOT / 'board' / 'board_state.json'
BOARD_IMAGE_FILE = PROJECT_ROOT / 'board' / 'board.png'


@dataclass
class Tile:
    """Represents a single tile on the bingo board"""
    number: int
    name: str
    gives_reroll: bool = False
    
    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "name": self.name,
            "gives_reroll": self.gives_reroll
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Tile':
        return cls(
            number=data["number"],
            name=data["name"],
            gives_reroll=data.get("gives_reroll", False)
        )


@dataclass
class Team:
    """Represents a team in the bingo game"""
    team_id: int
    name: str
    color: Tuple[int, int, int]
    players: List[str] = field(default_factory=list)
    discord_ids: List[str] = field(default_factory=list)
    position: int = 1  # 1-based tile number (matches JSON and display)
    rerolls: int = 1
    tile_completed: bool = True  # Whether current tile is completed (enables !roll)
    last_completed_position: int = 1  # Position before last roll (for rerolls), 1-based
    
    @property
    def tile_index(self) -> int:
        """Get 0-based array index for accessing tiles list"""
        return self.position - 1
    
    def to_dict(self) -> dict:
        return {
            "team_id": self.team_id,
            "name": self.name,
            "color": list(self.color),
            "players": self.players,
            "discord_ids": self.discord_ids,
            "position": self.position,
            "rerolls": self.rerolls,
            "tile_completed": self.tile_completed,
            "last_completed_position": self.last_completed_position
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Team':
        return cls(
            team_id=data["team_id"],
            name=data["name"],
            color=tuple(data["color"]),
            players=data.get("players", []),
            discord_ids=data.get("discord_ids", []),
            position=data.get("position", 1),  # 1-based, default to tile 1
            rerolls=data.get("rerolls", 1),
            tile_completed=data.get("tile_completed", True),
            last_completed_position=data.get("last_completed_position", 1)
        )


class BoardManager:
    """Manages the bingo board state, including tiles and teams"""
    
    def __init__(self):
        self.tiles: List[Tile] = []
        self.teams: List[Team] = []
        self._lock = threading.RLock()  # RLock allows reentrant locking (same thread can acquire multiple times)
        self._loaded = False
        
    def load_state(self) -> bool:
        """Load board state from JSON file"""
        with self._lock:
            try:
                if not BOARD_STATE_FILE.exists():
                    print(f"Board state file not found: {BOARD_STATE_FILE}")
                    return False
                
                with open(BOARD_STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.tiles = [Tile.from_dict(t) for t in data.get("tiles", [])]
                self.teams = [Team.from_dict(t) for t in data.get("teams", [])]
                self._loaded = True
                print(f"Loaded board state: {len(self.tiles)} tiles, {len(self.teams)} teams")
                return True
                
            except Exception as e:
                print(f"Error loading board state: {e}")
                return False
    
    def save_state(self) -> bool:
        """Save current board state to JSON file"""
        with self._lock:
            try:
                os.makedirs(BOARD_STATE_FILE.parent, exist_ok=True)
                
                data = {
                    "tiles": [t.to_dict() for t in self.tiles],
                    "teams": [t.to_dict() for t in self.teams]
                }
                
                with open(BOARD_STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                
                print(f"Saved board state: {len(self.tiles)} tiles, {len(self.teams)} teams")
                return True
                
            except Exception as e:
                print(f"Error saving board state: {e}")
                return False
    
    def get_tile(self, position: int) -> Optional[Tile]:
        """Get tile at given position (1-indexed, matching JSON/display)"""
        with self._lock:
            idx = position - 1  # Convert to 0-based index
            if 0 <= idx < len(self.tiles):
                return self.tiles[idx]
            return None
    
    def get_team(self, team_id: int) -> Optional[Team]:
        """Get team by ID"""
        with self._lock:
            for team in self.teams:
                if team.team_id == team_id:
                    return team
            return None
    
    def get_team_by_name(self, name: str) -> Optional[Team]:
        """Get team by name (case-insensitive)"""
        with self._lock:
            name_lower = name.lower()
            for team in self.teams:
                if team.name.lower() == name_lower:
                    return team
            return None
    
    def get_team_by_discord_id(self, discord_id: str) -> Optional[Team]:
        """Get team by Discord ID of a member"""
        with self._lock:
            for team in self.teams:
                if discord_id in team.discord_ids:
                    return team
            return None
    
    def update_team_position(self, team_id: int, new_position: int) -> bool:
        """Update a team's position on the board (1-indexed)"""
        team = self.get_team(team_id)
        if team and 1 <= new_position <= len(self.tiles):
            team.position = new_position
            return self.save_state()
        return False
    
    def update_team_rerolls(self, team_id: int, rerolls: int) -> bool:
        """Update a team's reroll count"""
        team = self.get_team(team_id)
        if team:
            team.rerolls = max(0, rerolls)
            return self.save_state()
        return False
    
    def add_reroll_to_team(self, team_id: int, amount: int = 1) -> bool:
        """Add rerolls to a team"""
        team = self.get_team(team_id)
        if team:
            team.rerolls += amount
            return self.save_state()
        return False
    
    def use_reroll(self, team_id: int) -> bool:
        """Use one reroll from a team (returns False if no rerolls available)"""
        team = self.get_team(team_id)
        if team and team.rerolls > 0:
            team.rerolls -= 1
            return self.save_state()
        return False
    
    def get_leaderboard(self) -> List[Team]:
        """Get teams sorted by position (highest first)"""
        with self._lock:
            return sorted(self.teams, key=lambda t: t.position, reverse=True)
    
    def get_teams_at_position(self, position: int) -> List[Team]:
        """Get all teams at a specific position"""
        with self._lock:
            return [team for team in self.teams if team.position == position]
    
    def register_team(self, team_id: int, discord_ids: List[str], player_names: List[str], 
                      name: Optional[str] = None, color: Optional[Tuple[int, int, int]] = None) -> bool:
        """Register or update a team with the given Discord user IDs and player names.
        
        Args:
            team_id: The unique team identifier
            discord_ids: List of Discord user IDs (as strings)
            player_names: List of display names for the players
            name: Optional team name (defaults to "Team {team_id}")
            color: Optional RGB color tuple (defaults to a generated color)
        
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                # First, remove any of these players from other teams
                for discord_id in discord_ids:
                    for team in self.teams:
                        if team.team_id != team_id and discord_id in team.discord_ids:
                            # Remove this player from the other team
                            idx = team.discord_ids.index(discord_id)
                            team.discord_ids.pop(idx)
                            team.players.pop(idx) if idx < len(team.players) else None
                
                # Check if team already exists (direct search, don't call get_team to avoid lock issues)
                existing_team = None
                for team in self.teams:
                    if team.team_id == team_id:
                        existing_team = team
                        break
                
                if existing_team:
                    # Update existing team
                    existing_team.discord_ids = discord_ids
                    existing_team.players = player_names
                    if name:
                        existing_team.name = name
                    if color:
                        existing_team.color = color
                else:
                    # Generate default color based on team_id if not provided
                    if color is None:
                        # Generate a unique color based on team_id
                        colors = [
                            (150, 20, 0),      # Red-brown
                            (210, 160, 40),    # Gold
                            (0, 105, 148),     # Blue
                            (100, 60, 30),     # Brown
                            (34, 139, 34),     # Green
                            (148, 0, 211),     # Purple
                            (255, 140, 0),     # Orange
                            (0, 206, 209),     # Cyan
                            (255, 20, 147),    # Pink
                            (50, 50, 50),      # Dark gray
                        ]
                        color = colors[(team_id - 1) % len(colors)]
                    
                    # Create new team (position=1 for 1-based tile numbering)
                    team_name = name if name else f"Team {team_id}"
                    new_team = Team(
                        team_id=team_id,
                        name=team_name,
                        color=color,
                        players=player_names,
                        discord_ids=discord_ids,
                        position=1,
                        rerolls=1
                    )
                    self.teams.append(new_team)
                
                return self.save_state()
                
            except Exception as e:
                print(f"Error registering team: {e}")
                return False
    
    def delete_team(self, team_id: int) -> bool:
        """Delete a team by ID.
        
        Args:
            team_id: The team identifier to delete
            
        Returns:
            True if team was deleted, False if team not found or error occurred
        """
        with self._lock:
            try:
                for i, team in enumerate(self.teams):
                    if team.team_id == team_id:
                        self.teams.pop(i)
                        return self.save_state()
                return False  # Team not found
                
            except Exception as e:
                print(f"Error deleting team: {e}")
                return False
    
    def is_loaded(self) -> bool:
        """Check if board state has been loaded"""
        return self._loaded


# Global singleton instance
board_manager = BoardManager()

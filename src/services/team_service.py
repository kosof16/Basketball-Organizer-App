"""Team generation service"""
import logging
import random
from typing import Optional, List

logger = logging.getLogger(__name__)


def generate_teams(df, game_id: int, num_teams: int = 2) -> Optional[List[List[str]]]:
    """
    Generate balanced teams from confirmed players

    Args:
        df: DataFrame with responses (passed to avoid circular imports)
        game_id: ID of the game
        num_teams: Number of teams to create

    Returns:
        List of teams (each team is a list of player names), or None if not enough players
    """
    try:
        # Filter confirmed players
        confirmed = df[df['status'] == '✅ Confirmed']

        # Collect all players
        players = []
        for _, row in confirmed.iterrows():
            players.append(row['name'])
            others_str = str(row.get('others', '') or '')
            for other in others_str.split(','):
                if other.strip():
                    players.append(other.strip())

        if len(players) < num_teams:
            return None

        # Shuffle for randomness
        random.shuffle(players)

        # Distribute players evenly
        teams = [[] for _ in range(num_teams)]
        for i, player in enumerate(players):
            teams[i % num_teams].append(player)

        return teams

    except Exception as e:
        logger.error(f"Error generating teams: {e}")
        return None

"""Enhanced waitlist management with auto-promotion"""
import logging
from typing import List, Dict, Optional
from datetime import datetime
from src.config import Config
from src.services.rsvp_service import load_responses, update_response_status
from src.services.notification_service import email_service

logger = logging.getLogger(__name__)


def get_waitlist_players(game_id: int) -> List[Dict]:
    """
    Get all players on the waitlist for a game

    Args:
        game_id: ID of the game

    Returns:
        List of waitlist player dictionaries
    """
    df = load_responses(game_id)
    waitlist_df = df[df['status'] == '⏳ Waitlist']

    waitlist = []
    for _, row in waitlist_df.iterrows():
        waitlist.append({
            'name': row['name'],
            'others': row.get('others', ''),
            'timestamp': row.get('timestamp', datetime.now()),
            'priority': calculate_waitlist_priority(row['name'])
        })

    # Sort by priority (higher first), then by timestamp (earlier first)
    waitlist.sort(key=lambda x: (-x['priority'], x['timestamp']))

    return waitlist


def calculate_waitlist_priority(player_name: str) -> int:
    """
    Calculate waitlist priority for a player based on their history

    Args:
        player_name: Name of the player

    Returns:
        Priority score (higher = higher priority)
    """
    try:
        from src.services.gamification_service import get_player_stats

        stats = get_player_stats(player_name)

        priority = 0

        # Base priority on attendance history
        priority += stats.get('games_attended', 0) * 10

        # Bonus for high attendance rate
        attendance_rate = stats.get('attendance_rate', 0)
        if attendance_rate >= 90:
            priority += 50
        elif attendance_rate >= 75:
            priority += 25

        # Bonus for current streak
        priority += stats.get('current_streak', 0) * 5

        # Penalty for cancellations
        priority -= stats.get('games_cancelled', 0) * 5

        # Penalty for no-shows
        priority -= stats.get('games_no_show', 0) * 15

        return max(0, priority)

    except Exception as e:
        logger.error(f"Error calculating waitlist priority: {e}")
        return 0


def count_confirmed_players(game_id: int) -> int:
    """
    Count total confirmed players including guests

    Args:
        game_id: ID of the game

    Returns:
        Total number of confirmed players
    """
    df = load_responses(game_id)
    confirmed_df = df[df['status'] == '✅ Confirmed']

    total = 0
    for _, row in confirmed_df.iterrows():
        # Count main player
        total += 1

        # Count guests
        others_str = str(row.get('others', '') or '')
        guests = [g.strip() for g in others_str.split(',') if g.strip()]
        total += len(guests)

    return total


def get_available_spots(game_id: int) -> int:
    """
    Get number of available spots for a game

    Args:
        game_id: ID of the game

    Returns:
        Number of available spots
    """
    confirmed_count = count_confirmed_players(game_id)
    return max(0, Config.CAPACITY - confirmed_count)


def can_promote_from_waitlist(game_id: int, player_name: str, guest_count: int = 0) -> bool:
    """
    Check if a player can be promoted from waitlist

    Args:
        game_id: ID of the game
        player_name: Name of the player
        guest_count: Number of guests the player is bringing

    Returns:
        True if can be promoted, False otherwise
    """
    available_spots = get_available_spots(game_id)
    required_spots = 1 + guest_count

    return available_spots >= required_spots


def promote_from_waitlist(game_id: int, game_details: Dict = None, notify: bool = True) -> List[str]:
    """
    Auto-promote players from waitlist when spots become available

    Args:
        game_id: ID of the game
        game_details: Game details for notifications
        notify: Whether to send email notifications

    Returns:
        List of promoted player names
    """
    promoted_players = []
    available_spots = get_available_spots(game_id)

    if available_spots <= 0:
        return promoted_players

    waitlist = get_waitlist_players(game_id)

    for player in waitlist:
        if available_spots <= 0:
            break

        # Count spots needed (player + guests)
        others_str = player['others'] or ''
        guests = [g.strip() for g in others_str.split(',') if g.strip()]
        spots_needed = 1 + len(guests)

        # Check if we have enough spots
        if spots_needed <= available_spots:
            # Promote player
            if update_response_status(game_id, [player['name']], '✅ Confirmed'):
                promoted_players.append(player['name'])
                available_spots -= spots_needed

                logger.info(f"Promoted from waitlist: {player['name']} (Game {game_id})")

                # Send notification
                if notify and game_details:
                    try:
                        # Try to get email from player profile (if implemented)
                        # For now, we'll skip email sending as we don't have email addresses
                        # In production, you'd look up player email from database
                        logger.info(f"Would send waitlist promotion email to {player['name']}")

                        # Update gamification stats
                        from src.services.gamification_service import update_player_stats
                        update_player_stats(
                            player['name'],
                            "promoted_from_waitlist",
                            {"game_id": game_id}
                        )

                    except Exception as e:
                        logger.error(f"Error sending promotion notification: {e}")

    return promoted_players


def handle_cancellation_promotion(game_id: int, game_details: Dict = None) -> List[str]:
    """
    Handle auto-promotion when a player cancels

    Args:
        game_id: ID of the game
        game_details: Game details for notifications

    Returns:
        List of promoted player names
    """
    return promote_from_waitlist(game_id, game_details, notify=True)


def get_waitlist_position(game_id: int, player_name: str) -> Optional[int]:
    """
    Get player's position in the waitlist

    Args:
        game_id: ID of the game
        player_name: Name of the player

    Returns:
        Position in waitlist (1-indexed), or None if not on waitlist
    """
    waitlist = get_waitlist_players(game_id)

    for position, player in enumerate(waitlist, start=1):
        if player['name'] == player_name:
            return position

    return None


def get_waitlist_stats(game_id: int) -> Dict:
    """
    Get comprehensive waitlist statistics

    Args:
        game_id: ID of the game

    Returns:
        Dictionary with waitlist stats
    """
    waitlist = get_waitlist_players(game_id)
    confirmed_count = count_confirmed_players(game_id)
    available_spots = get_available_spots(game_id)

    return {
        "waitlist_count": len(waitlist),
        "confirmed_count": confirmed_count,
        "available_spots": available_spots,
        "capacity": Config.CAPACITY,
        "utilization_percent": (confirmed_count / Config.CAPACITY * 100) if Config.CAPACITY > 0 else 0,
        "next_to_promote": waitlist[0]['name'] if waitlist else None
    }


def notify_waitlist_status(game_id: int, player_name: str, position: int) -> bool:
    """
    Notify player of their waitlist status

    Args:
        game_id: ID of the game
        player_name: Name of the player
        position: Position in waitlist

    Returns:
        True if notification sent, False otherwise
    """
    try:
        # In production, look up player email and send notification
        logger.info(f"Waitlist notification: {player_name} is #{position} on waitlist for game {game_id}")

        # Update gamification
        from src.services.gamification_service import update_player_stats
        update_player_stats(
            player_name,
            "added_to_waitlist",
            {"game_id": game_id, "position": position}
        )

        return True

    except Exception as e:
        logger.error(f"Error sending waitlist notification: {e}")
        return False

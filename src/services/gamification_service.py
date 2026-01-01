"""Gamification service for player engagement and achievements"""
import logging
import streamlit as st
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

# Achievement definitions
ACHIEVEMENTS = {
    "first_game": {
        "name": "🏀 First Timer",
        "description": "Attended your first game",
        "points": 10,
        "icon": "🏀",
        "requirement": lambda stats: stats['games_attended'] >= 1
    },
    "regular": {
        "name": "⭐ Court Regular",
        "description": "Attended 10+ games",
        "points": 50,
        "icon": "⭐",
        "requirement": lambda stats: stats['games_attended'] >= 10
    },
    "veteran": {
        "name": "👑 Court Veteran",
        "description": "Attended 25+ games",
        "points": 150,
        "icon": "👑",
        "requirement": lambda stats: stats['games_attended'] >= 25
    },
    "legend": {
        "name": "🏆 Court Legend",
        "description": "Attended 50+ games",
        "points": 300,
        "icon": "🏆",
        "requirement": lambda stats: stats['games_attended'] >= 50
    },
    "reliable": {
        "name": "💎 Reliable Player",
        "description": "90%+ attendance rate (min 5 games)",
        "points": 75,
        "icon": "💎",
        "requirement": lambda stats: stats['games_attended'] >= 5 and stats['attendance_rate'] >= 90
    },
    "perfect_attendance": {
        "name": "✨ Perfect Record",
        "description": "100% attendance rate (min 10 games)",
        "points": 200,
        "icon": "✨",
        "requirement": lambda stats: stats['games_attended'] >= 10 and stats['attendance_rate'] == 100
    },
    "hot_streak": {
        "name": "🔥 Hot Streak",
        "description": "Attended 5 consecutive games",
        "points": 40,
        "icon": "🔥",
        "requirement": lambda stats: stats.get('current_streak', 0) >= 5
    },
    "early_bird": {
        "name": "🌅 Early Bird",
        "description": "RSVP'd early 10+ times",
        "points": 30,
        "icon": "🌅",
        "requirement": lambda stats: stats.get('early_rsvps', 0) >= 10
    },
    "team_player": {
        "name": "🤝 Team Player",
        "description": "Brought 5+ guests",
        "points": 25,
        "icon": "🤝",
        "requirement": lambda stats: stats.get('guests_brought', 0) >= 5
    },
    "mvp": {
        "name": "🌟 Season MVP",
        "description": "Highest attendance this month",
        "points": 100,
        "icon": "🌟",
        "requirement": lambda stats: stats.get('is_monthly_mvp', False)
    }
}

# Points system
POINTS_CONFIG = {
    "rsvp_confirmed": 10,
    "rsvp_early": 5,  # Bonus for RSVP >24h in advance
    "attendance": 20,
    "brought_guest": 5,
    "late_cancel": -5,
    "no_show": -10,
    "streak_bonus": 5  # Per consecutive game
}


def init_gamification_storage():
    """Initialize gamification data in session state"""
    if "player_stats" not in st.session_state:
        st.session_state.player_stats = {}
    if "player_achievements" not in st.session_state:
        st.session_state.player_achievements = {}
    if "player_points" not in st.session_state:
        st.session_state.player_points = {}


def get_player_stats(player_name: str) -> Dict:
    """
    Get comprehensive stats for a player

    Args:
        player_name: Name of the player

    Returns:
        Dictionary with player statistics
    """
    init_gamification_storage()

    if player_name not in st.session_state.player_stats:
        st.session_state.player_stats[player_name] = {
            "games_rsvp": 0,
            "games_attended": 0,
            "games_cancelled": 0,
            "games_no_show": 0,
            "early_rsvps": 0,
            "guests_brought": 0,
            "current_streak": 0,
            "longest_streak": 0,
            "last_game_date": None,
            "first_game_date": None,
            "attendance_rate": 0.0,
            "total_points": 0,
            "is_monthly_mvp": False
        }

    return st.session_state.player_stats[player_name]


def update_player_stats(player_name: str, action: str, details: Dict = None):
    """
    Update player statistics based on action

    Args:
        player_name: Name of the player
        action: Action type (rsvp, attend, cancel, etc.)
        details: Additional details about the action
    """
    init_gamification_storage()
    stats = get_player_stats(player_name)
    details = details or {}

    if action == "rsvp_confirmed":
        stats["games_rsvp"] += 1
        points = POINTS_CONFIG["rsvp_confirmed"]

        # Check if early RSVP (>24h in advance)
        if details.get("is_early", False):
            stats["early_rsvps"] += 1
            points += POINTS_CONFIG["rsvp_early"]

        # Track guests
        guests = details.get("guests_count", 0)
        if guests > 0:
            stats["guests_brought"] += guests
            points += guests * POINTS_CONFIG["brought_guest"]

        add_points(player_name, points, f"RSVP for game")

    elif action == "attendance_confirmed":
        stats["games_attended"] += 1

        # Update streak
        last_date = stats.get("last_game_date")
        current_date = details.get("game_date")

        if last_date and current_date:
            # Check if consecutive (allow up to 14 days gap)
            from datetime import datetime, timedelta
            if isinstance(last_date, str):
                last_date = datetime.fromisoformat(last_date).date()
            if isinstance(current_date, str):
                current_date = datetime.fromisoformat(current_date).date()

            days_diff = (current_date - last_date).days
            if days_diff <= 14:
                stats["current_streak"] += 1
            else:
                stats["current_streak"] = 1
        else:
            stats["current_streak"] = 1

        stats["longest_streak"] = max(stats["longest_streak"], stats["current_streak"])
        stats["last_game_date"] = current_date.isoformat() if hasattr(current_date, 'isoformat') else current_date

        if not stats["first_game_date"]:
            stats["first_game_date"] = current_date.isoformat() if hasattr(current_date, 'isoformat') else current_date

        # Award points
        points = POINTS_CONFIG["attendance"]
        if stats["current_streak"] > 1:
            streak_bonus = (stats["current_streak"] - 1) * POINTS_CONFIG["streak_bonus"]
            points += streak_bonus

        add_points(player_name, points, f"Attended game")

    elif action == "cancelled":
        stats["games_cancelled"] += 1
        stats["current_streak"] = 0

        # Late cancellation penalty
        if details.get("is_late", False):
            add_points(player_name, POINTS_CONFIG["late_cancel"], "Late cancellation")

    elif action == "no_show":
        stats["games_no_show"] += 1
        stats["current_streak"] = 0
        add_points(player_name, POINTS_CONFIG["no_show"], "No show")

    # Recalculate attendance rate
    total_games = stats["games_attended"] + stats["games_cancelled"] + stats["games_no_show"]
    if total_games > 0:
        stats["attendance_rate"] = (stats["games_attended"] / total_games) * 100

    # Update total points
    stats["total_points"] = get_player_points(player_name)

    # Check for new achievements
    check_achievements(player_name)

    st.session_state.player_stats[player_name] = stats


def add_points(player_name: str, points: int, reason: str = ""):
    """
    Add points to a player's score

    Args:
        player_name: Name of the player
        points: Points to add (can be negative)
        reason: Reason for points
    """
    init_gamification_storage()

    if player_name not in st.session_state.player_points:
        st.session_state.player_points[player_name] = []

    st.session_state.player_points[player_name].append({
        "points": points,
        "reason": reason,
        "timestamp": datetime.now().isoformat()
    })

    logger.info(f"Points awarded: {player_name} +{points} - {reason}")


def get_player_points(player_name: str) -> int:
    """Get total points for a player"""
    init_gamification_storage()

    if player_name not in st.session_state.player_points:
        return 0

    return sum(entry["points"] for entry in st.session_state.player_points[player_name])


def check_achievements(player_name: str) -> List[str]:
    """
    Check and award new achievements for a player

    Args:
        player_name: Name of the player

    Returns:
        List of newly earned achievement IDs
    """
    init_gamification_storage()
    stats = get_player_stats(player_name)

    if player_name not in st.session_state.player_achievements:
        st.session_state.player_achievements[player_name] = []

    current_achievements = st.session_state.player_achievements[player_name]
    new_achievements = []

    for achievement_id, achievement in ACHIEVEMENTS.items():
        # Skip if already earned
        if achievement_id in current_achievements:
            continue

        # Check if requirement met
        if achievement["requirement"](stats):
            current_achievements.append(achievement_id)
            new_achievements.append(achievement_id)

            # Award achievement points
            add_points(player_name, achievement["points"],
                      f"Achievement: {achievement['name']}")

            logger.info(f"Achievement unlocked: {player_name} - {achievement['name']}")

    if new_achievements:
        st.session_state.player_achievements[player_name] = current_achievements

    return new_achievements


def get_player_achievements(player_name: str) -> List[Dict]:
    """Get all achievements for a player with details"""
    init_gamification_storage()

    if player_name not in st.session_state.player_achievements:
        return []

    achievement_ids = st.session_state.player_achievements[player_name]
    return [
        {**ACHIEVEMENTS[aid], "id": aid, "earned_date": "Recent"}
        for aid in achievement_ids
    ]


def get_leaderboard(metric: str = "points", limit: int = 10) -> List[Tuple[str, int]]:
    """
    Get leaderboard for a specific metric

    Args:
        metric: Metric to rank by (points, games_attended, attendance_rate, streak)
        limit: Number of players to return

    Returns:
        List of (player_name, value) tuples
    """
    init_gamification_storage()

    rankings = []

    if metric == "points":
        for player_name in st.session_state.player_points.keys():
            total_points = get_player_points(player_name)
            rankings.append((player_name, total_points))
    else:
        for player_name, stats in st.session_state.player_stats.items():
            value = stats.get(metric, 0)
            rankings.append((player_name, value))

    # Sort descending
    rankings.sort(key=lambda x: x[1], reverse=True)

    return rankings[:limit]


def get_player_rank(player_name: str, metric: str = "points") -> int:
    """Get player's rank for a specific metric"""
    leaderboard = get_leaderboard(metric, limit=1000)

    for rank, (name, _) in enumerate(leaderboard, start=1):
        if name == player_name:
            return rank

    return 0


def calculate_monthly_mvp():
    """Calculate and award monthly MVP"""
    init_gamification_storage()

    # Find player with most attendance this month
    current_month = datetime.now().strftime("%Y-%m")

    # This is a simplified version - in production, track monthly stats
    leaderboard = get_leaderboard("games_attended", limit=1)

    if leaderboard:
        mvp_name = leaderboard[0][0]
        stats = get_player_stats(mvp_name)
        stats["is_monthly_mvp"] = True
        check_achievements(mvp_name)

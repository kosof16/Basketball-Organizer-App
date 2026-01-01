"""Game management service"""
import logging
import streamlit as st
from datetime import date, time
from typing import Optional, Dict, Any
from src.models.database import get_connection, release_connection

logger = logging.getLogger(__name__)


def save_game_session(game_date: date, start_time: time, end_time: time, location: str) -> bool:
    """Save game to session state"""
    try:
        game_id = len(st.session_state.get('games', [])) + 1
        game = {
            'id': game_id,
            'game_date': game_date,
            'start_time': start_time,
            'end_time': end_time,
            'location': location,
            'is_active': True
        }
        st.session_state.current_game = game
        return True
    except Exception as e:
        logger.error(f"Error saving game to session: {e}")
        return False


def load_current_game_session() -> Optional[Dict[str, Any]]:
    """Load current game from session state"""
    return st.session_state.get('current_game')


def save_game(game_date: date, start_time: time, end_time: time, location: str) -> bool:
    """
    Save game with database fallback to session state

    Args:
        game_date: Date of the game
        start_time: Start time of the game
        end_time: End time of the game
        location: Game location

    Returns:
        True if successful, False otherwise
    """
    from src.config import Config

    db_config = Config.get_database_config()
    conn, db_type = get_connection(db_config)

    if db_type == "session":
        return save_game_session(game_date, start_time, end_time, location)

    try:
        cur = conn.cursor()

        # Deactivate current games
        if db_type == "postgresql":
            cur.execute("UPDATE games SET is_active = FALSE WHERE is_active = TRUE")
            cur.execute("""
                INSERT INTO games (game_date, start_time, end_time, location)
                VALUES (%s, %s, %s, %s)
            """, (game_date, start_time, end_time, location))
        else:  # SQLite
            cur.execute("UPDATE games SET is_active = 0 WHERE is_active = 1")
            cur.execute("""
                INSERT INTO games (game_date, start_time, end_time, location)
                VALUES (?, ?, ?, ?)
            """, (str(game_date), str(start_time), str(end_time), location))

        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error saving game: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
    finally:
        release_connection(conn, db_type)


def load_current_game() -> Optional[Dict[str, Any]]:
    """
    Load current active game

    Returns:
        Game dictionary or None if no active game
    """
    from src.config import Config

    db_config = Config.get_database_config()
    conn, db_type = get_connection(db_config)

    if db_type == "session":
        return load_current_game_session()

    try:
        cur = conn.cursor()

        if db_type == "postgresql":
            cur.execute("""
                SELECT * FROM games
                WHERE is_active = TRUE
                ORDER BY created_at DESC
                LIMIT 1
            """)
        else:  # SQLite
            cur.execute("""
                SELECT * FROM games
                WHERE is_active = 1
                ORDER BY created_at DESC
                LIMIT 1
            """)

        row = cur.fetchone()
        cur.close()

        if row:
            if db_type == "postgresql":
                return dict(row) if hasattr(row, '__dict__') else {
                    'id': row[0],
                    'game_date': row[1],
                    'start_time': row[2],
                    'end_time': row[3],
                    'location': row[4],
                    'created_at': row[5],
                    'is_active': row[6]
                }
            else:  # SQLite
                return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error loading game: {e}")
        return None
    finally:
        release_connection(conn, db_type)

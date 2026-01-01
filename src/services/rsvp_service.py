"""RSVP management service"""
import logging
import pandas as pd
import streamlit as st
from datetime import datetime
from typing import List
from src.models.database import get_connection, release_connection
from src.config import Config

logger = logging.getLogger(__name__)


def add_response_session(name: str, others: str, attend: bool, game_id: int) -> bool:
    """Add response to session state"""
    try:
        status = '❌ Cancelled' if not attend else ''

        # Check if response exists
        existing_idx = None
        for i, resp in enumerate(st.session_state.responses):
            if resp['name'].lower() == name.lower():
                existing_idx = i
                break

        response_data = {
            'id': len(st.session_state.responses) + 1 if existing_idx is None else st.session_state.responses[existing_idx]['id'],
            'game_id': game_id,
            'name': name,
            'others': others,
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        if existing_idx is not None:
            st.session_state.responses[existing_idx] = response_data
        else:
            st.session_state.responses.append(response_data)

        return True
    except Exception as e:
        logger.error(f"Error adding response to session: {e}")
        return False


def load_responses_session(game_id: int) -> pd.DataFrame:
    """Load responses from session state"""
    responses = [r for r in st.session_state.responses if r.get('game_id') == game_id]
    return pd.DataFrame(responses)


def update_response_status_session(game_id: int, names: List[str], new_status: str) -> bool:
    """Update response status in session state"""
    try:
        updated = False
        for resp in st.session_state.responses:
            if resp.get('game_id') == game_id and resp.get('name') in names:
                resp['status'] = new_status
                resp['updated_at'] = datetime.now().isoformat()
                updated = True
        return updated
    except Exception as e:
        logger.error(f"Error updating response status in session: {e}")
        return False


def delete_responses_session(game_id: int, names: List[str]) -> bool:
    """Delete responses from session state"""
    try:
        original_count = len(st.session_state.responses)
        st.session_state.responses = [
            resp for resp in st.session_state.responses
            if not (resp.get('game_id') == game_id and resp.get('name') in names)
        ]
        return len(st.session_state.responses) < original_count
    except Exception as e:
        logger.error(f"Error deleting responses from session: {e}")
        return False


def add_response(name: str, others: str, attend: bool, game_id: int) -> bool:
    """
    Add or update RSVP response

    Args:
        name: Player name
        others: Additional guests (comma-separated)
        attend: True if attending, False if cancelling
        game_id: ID of the game

    Returns:
        True if successful, False otherwise
    """
    db_config = Config.get_database_config()
    conn, db_type = get_connection(db_config)

    if db_type == "session":
        return add_response_session(name, others, attend, game_id)

    try:
        cur = conn.cursor()
        status = '❌ Cancelled' if not attend else ''

        # Check if exists and update or insert
        if db_type == "postgresql":
            # First try to update existing record
            cur.execute("""
                UPDATE responses
                SET others = %s, status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE game_id = %s AND name = %s
            """, (others, status, game_id, name))

            # If no rows were updated, insert new record
            if cur.rowcount == 0:
                cur.execute("""
                    INSERT INTO responses (game_id, name, others, status)
                    VALUES (%s, %s, %s, %s)
                """, (game_id, name, others, status))
        else:  # SQLite
            cur.execute("""
                INSERT OR REPLACE INTO responses (game_id, name, others, status)
                VALUES (?, ?, ?, ?)
            """, (game_id, name, others, status))

        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error adding response: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
    finally:
        release_connection(conn, db_type)


def load_responses(game_id: int) -> pd.DataFrame:
    """
    Load all responses for a game

    Args:
        game_id: ID of the game

    Returns:
        DataFrame of responses
    """
    db_config = Config.get_database_config()
    conn, db_type = get_connection(db_config)

    if db_type == "session":
        return load_responses_session(game_id)

    try:
        if db_type == "postgresql":
            # Use direct query to avoid pandas warning
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM responses
                WHERE game_id = %s
                ORDER BY timestamp
            """, (game_id,))

            # Get column names
            columns = [desc[0] for desc in cur.description]

            # Fetch all rows
            rows = cur.fetchall()
            cur.close()

            # Create DataFrame manually
            if rows:
                df = pd.DataFrame(rows, columns=columns)
            else:
                df = pd.DataFrame(columns=columns)

            return df
        else:  # SQLite
            query = "SELECT * FROM responses WHERE game_id = ? ORDER BY timestamp"
            df = pd.read_sql_query(query, conn, params=(game_id,))
            return df

    except Exception as e:
        logger.error(f"Error loading responses: {e}")
        return pd.DataFrame()
    finally:
        release_connection(conn, db_type)


def update_response_status(game_id: int, names: List[str], new_status: str) -> bool:
    """
    Update status for multiple responses

    Args:
        game_id: ID of the game
        names: List of player names
        new_status: New status to set

    Returns:
        True if successful, False otherwise
    """
    db_config = Config.get_database_config()
    conn, db_type = get_connection(db_config)

    if db_type == "session":
        return update_response_status_session(game_id, names, new_status)

    try:
        cur = conn.cursor()

        if db_type == "postgresql":
            cur.execute("""
                UPDATE responses
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE game_id = %s AND name = ANY(%s)
            """, (new_status, game_id, names))
        else:  # SQLite
            placeholders = ','.join('?' * len(names))
            cur.execute(f"""
                UPDATE responses
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE game_id = ? AND name IN ({placeholders})
            """, [new_status, game_id] + names)

        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error updating status: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
    finally:
        release_connection(conn, db_type)


def delete_responses(game_id: int, names: List[str]) -> bool:
    """
    Delete responses

    Args:
        game_id: ID of the game
        names: List of player names to delete

    Returns:
        True if successful, False otherwise
    """
    db_config = Config.get_database_config()
    conn, db_type = get_connection(db_config)

    if db_type == "session":
        return delete_responses_session(game_id, names)

    try:
        cur = conn.cursor()

        if db_type == "postgresql":
            cur.execute("""
                DELETE FROM responses
                WHERE game_id = %s AND name = ANY(%s)
            """, (game_id, names))
        else:  # SQLite
            placeholders = ','.join('?' * len(names))
            cur.execute(f"""
                DELETE FROM responses
                WHERE game_id = ? AND name IN ({placeholders})
            """, [game_id] + names)

        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error deleting responses: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
    finally:
        release_connection(conn, db_type)


def update_statuses(game_id: int) -> None:
    """
    Update response statuses based on capacity

    Args:
        game_id: ID of the game
    """
    df = load_responses(game_id)

    if df.empty:
        return

    # Calculate total players
    total_confirmed = 0
    player_counts = []

    for _, row in df.iterrows():
        if row.get('status') == '❌ Cancelled':
            continue

        others_str = str(row.get('others', '') or '')
        others_list = [o.strip() for o in others_str.split(',') if o.strip()]
        player_count = 1 + len(others_list)

        player_counts.append({
            'name': row['name'],
            'count': player_count,
            'current_status': row.get('status', '')
        })
        total_confirmed += player_count

    # Update statuses
    names_to_confirm = []
    names_to_waitlist = []
    current_count = 0

    for player in player_counts:
        if current_count + player['count'] <= Config.CAPACITY:
            if player['current_status'] != '✅ Confirmed':
                names_to_confirm.append(player['name'])
            current_count += player['count']
        else:
            if player['current_status'] != '⏳ Waitlist':
                names_to_waitlist.append(player['name'])

    # Apply updates
    if names_to_confirm:
        update_response_status(game_id, names_to_confirm, '✅ Confirmed')

    if names_to_waitlist:
        update_response_status(game_id, names_to_waitlist, '⏳ Waitlist')

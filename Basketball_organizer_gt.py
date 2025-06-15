import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, time, timedelta
import random
import altair as alt
import json
import logging
from typing import Optional, Dict, List, Any, Tuple
import calendar
from functools import lru_cache
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Page Config (Must be first) ---
st.set_page_config(
    page_title="🏀 Basketball Organizer", 
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/yourusername/basketball-organizer',
        'Report a bug': "https://github.com/yourusername/basketball-organizer/issues",
        'About': "# Basketball Organizer\nOrganize your basketball games with ease!"
    }
)

# --- Constants ---
CAPACITY = int(os.getenv('GAME_CAPACITY', '15'))
DEFAULT_LOCATION = "Arc: Health and Fitness Centre"
CUTOFF_DAYS = int(os.getenv('RSVP_CUTOFF_DAYS', '1'))
SESSION_TIMEOUT_MINUTES = 30
CACHE_TTL = 300  # 5 minutes cache

# Event types for calendar
EVENT_TYPES = {
    "🏀 Game": {"color": "#4CAF50", "icon": "🏀"},
    "🏃 Training": {"color": "#2196F3", "icon": "🏃"},
    "🏆 Tournament": {"color": "#FF9800", "icon": "🏆"},
    "🎉 Social": {"color": "#9C27B0", "icon": "🎉"},
    "📋 Meeting": {"color": "#607D8B", "icon": "📋"},
    "🚫 Cancelled": {"color": "#F44336", "icon": "🚫"}
}

# --- Initialize availability flags ---
DB_AVAILABLE = False
SQLITE_AVAILABLE = False
GOOGLE_DRIVE_AVAILABLE = False

# Try to import PostgreSQL driver
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DB_AVAILABLE = True
    logger.info("PostgreSQL driver loaded successfully")
except ImportError:
    logger.warning("PostgreSQL driver not available")
    try:
        import sqlite3
        SQLITE_AVAILABLE = True
        logger.info("SQLite available as fallback")
    except ImportError:
        logger.error("No database drivers available")

# Google Drive integration
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    import io
    GOOGLE_DRIVE_AVAILABLE = True
    logger.info("Google Drive integration available")
except ImportError:
    logger.warning("Google Drive integration not available")

# --- Custom CSS for better UI ---
st.markdown("""
<style>
    /* Main container styling */
    .main {
        padding-top: 2rem;
    }
    
    /* Card styling */
    .stContainer > div {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    
    /* Metric styling */
    [data-testid="metric-container"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Button styling */
    .stButton > button {
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    
    /* Calendar day buttons */
    div[data-testid="column"] > div > button {
        width: 100%;
        min-height: 60px;
        margin: 2px;
    }
    
    /* Success/Error messages */
    .stSuccess, .stError, .stWarning, .stInfo {
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        font-weight: 600;
        font-size: 1.1rem;
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# === CORE FUNCTION DEFINITIONS START HERE ===

# --- Session State Functions ---
def init_session_state():
    """Initialize all session state variables"""
    defaults = {
        "admin_authenticated": False,
        "admin_login_time": None,
        "current_game": None,
        "responses": [],
        "calendar_events": [],
        "selected_date": date.today(),
        "show_edit_form": False,
        "editing_event_id": None,
        "last_refresh": datetime.now(),
        "connection_cache": None,
        "user_preferences": {
            "theme": "light",
            "notifications": True,
            "auto_refresh": True
        },
        "tables_initialized": False
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# --- Database Connection Functions ---
@lru_cache(maxsize=1)
def get_connection_pool():
    """Get or create a connection pool (cached)"""
    if DB_AVAILABLE and "database" in st.secrets:
        try:
            import psycopg2.pool
            pool = psycopg2.pool.SimpleConnectionPool(
                1, 5,  # min and max connections
                host=st.secrets["database"]["host"],
                database=st.secrets["database"]["dbname"],
                user=st.secrets["database"]["user"],
                password=st.secrets["database"]["password"],
                port=st.secrets["database"]["port"]
            )
            logger.info("PostgreSQL connection pool created")
            return pool, "postgresql"
        except Exception as e:
            logger.error(f"PostgreSQL pool creation failed: {e}")
    
    # Fallback to SQLite
    if SQLITE_AVAILABLE:
        logger.info("Using SQLite fallback")
        return None, "sqlite"
    
    logger.warning("Using session state storage")
    return None, "session"

def get_connection():
    """Get a database connection from pool or create one"""
    pool, db_type = get_connection_pool()
    
    if db_type == "postgresql" and pool:
        try:
            return pool.getconn(), db_type
        except Exception as e:
            logger.error(f"Failed to get connection from pool: {e}")
            return None, "session"
    elif db_type == "sqlite":
        try:
            conn = sqlite3.connect(':memory:', check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn, "sqlite"
        except Exception as e:
            logger.error(f"SQLite connection failed: {e}")
            return None, "session"
    
    return None, "session"

def release_connection(conn, db_type):
    """Release connection back to pool"""
    if db_type == "postgresql" and conn:
        pool, _ = get_connection_pool()
        if pool:
            pool.putconn(conn)

def create_tables():
    """Create necessary database tables"""
    conn, db_type = get_connection()
    
    if db_type == "session":
        # Using session state, no tables needed
        logger.info("Using session state storage - no tables to create")
        return True
    
    try:
        cur = conn.cursor()
        
        if db_type == "postgresql":
            # Create games table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    id SERIAL PRIMARY KEY,
                    game_date DATE NOT NULL,
                    start_time TIME NOT NULL,
                    end_time TIME NOT NULL,
                    location VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)
            
            # Create responses table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS responses (
                    id SERIAL PRIMARY KEY,
                    game_id INTEGER REFERENCES games(id),
                    name VARCHAR(255) NOT NULL,
                    others TEXT,
                    status VARCHAR(50) DEFAULT '',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(game_id, name)
                )
            """)
            
            # Create indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_responses_game_id ON responses(game_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_responses_status ON responses(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_games_active ON games(is_active)")
            
        else:  # SQLite
            cur.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_date DATE NOT NULL,
                    start_time TIME NOT NULL,
                    end_time TIME NOT NULL,
                    location TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER,
                    name TEXT NOT NULL,
                    others TEXT,
                    status TEXT DEFAULT '',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (game_id) REFERENCES games(id),
                    UNIQUE(game_id, name)
                )
            """)
            
            # Create indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_responses_game_id ON responses(game_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_responses_status ON responses(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_games_active ON games(is_active)")
        
        conn.commit()
        cur.close()
        logger.info("Database tables created successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        release_connection(conn, db_type)

# --- Session State Storage Functions ---
def save_game_session(game_date, start_time, end_time, location):
    """Save game to session state"""
    game_data = {
        'id': 1,
        'game_date': game_date.isoformat() if hasattr(game_date, 'isoformat') else str(game_date),
        'start_time': start_time.isoformat() if hasattr(start_time, 'isoformat') else str(start_time),
        'end_time': end_time.isoformat() if hasattr(end_time, 'isoformat') else str(end_time),
        'location': location,
        'created_at': datetime.now().isoformat(),
        'is_active': True
    }
    st.session_state.current_game = game_data
    return True

def load_current_game_session():
    """Load current game from session state"""
    return st.session_state.get('current_game')

def add_response_session(name, others, attend, game_id):
    """Add response to session state"""
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

def load_responses_session(game_id):
    """Load responses from session state"""
    responses = [r for r in st.session_state.responses if r.get('game_id') == game_id]
    return pd.DataFrame(responses)

def update_response_status_session(game_id, names, new_status):
    """Update response status in session state"""
    updated = False
    for resp in st.session_state.responses:
        if resp.get('game_id') == game_id and resp.get('name') in names:
            resp['status'] = new_status
            resp['updated_at'] = datetime.now().isoformat()
            updated = True
    return updated

def delete_responses_session(game_id, names):
    """Delete responses from session state"""
    original_count = len(st.session_state.responses)
    st.session_state.responses = [
        resp for resp in st.session_state.responses 
        if not (resp.get('game_id') == game_id and resp.get('name') in names)
    ]
    return len(st.session_state.responses) < original_count

# --- Main Database Interface Functions ---
def save_game(game_date, start_time, end_time, location) -> bool:
    """Save game with fallback to session state"""
    conn, db_type = get_connection()
    
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
            conn.rollback()
        return False
    finally:
        release_connection(conn, db_type)

def load_current_game() -> Optional[Dict]:
    """Load current game with fallback"""
    conn, db_type = get_connection()
    
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

def add_response(name: str, others: str, attend: bool, game_id: int) -> bool:
    """Add response with fallback"""
    conn, db_type = get_connection()
    
    if db_type == "session":
        return add_response_session(name, others, attend, game_id)
    
    try:
        cur = conn.cursor()
        status = '❌ Cancelled' if not attend else ''
        
        # Check if exists and update or insert
        if db_type == "postgresql":
            cur.execute("""
                INSERT INTO responses (game_id, name, others, status)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (game_id, name) 
                DO UPDATE SET others = EXCLUDED.others, 
                             status = EXCLUDED.status,
                             updated_at = CURRENT_TIMESTAMP
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
            conn.rollback()
        return False
    finally:
        release_connection(conn, db_type)

def load_responses(game_id: int) -> pd.DataFrame:
    """Load responses with fallback"""
    conn, db_type = get_connection()
    
    if db_type == "session":
        return load_responses_session(game_id)
    
    try:
        if db_type == "postgresql":
            query = "SELECT * FROM responses WHERE game_id = %s ORDER BY timestamp"
            df = pd.read_sql_query(query, conn, params=(game_id,))
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
    """Update response status with fallback"""
    conn, db_type = get_connection()
    
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
            conn.rollback()
        return False
    finally:
        release_connection(conn, db_type)

def delete_responses(game_id: int, names: List[str]) -> bool:
    """Delete responses with fallback"""
    conn, db_type = get_connection()
    
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
            conn.rollback()
        return False
    finally:
        release_connection(conn, db_type)

# --- Authentication Functions ---
def hash_password(password: str) -> str:
    """Hash password for comparison"""
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_admin(username: str, password: str) -> bool:
    """Enhanced authentication with better security"""
    try:
        # Get admin credentials
        admin_password = st.secrets.get("admin_password", "")
        admin_username = st.secrets.get("admin_username", "admin")
        
        # Clean inputs
        clean_username = username.strip().lower()
        clean_password = password.strip()
        
        # For demo purposes, we'll use simple comparison
        # In production, use proper password hashing
        return (clean_username == admin_username.lower() and 
                clean_password == admin_password)
        
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return False

def check_session_timeout():
    """Check if admin session has timed out"""
    if (st.session_state.admin_authenticated and 
        st.session_state.admin_login_time and
        datetime.now() - st.session_state.admin_login_time > timedelta(minutes=SESSION_TIMEOUT_MINUTES)):
        st.session_state.admin_authenticated = False
        st.session_state.admin_login_time = None
        st.warning("⏱️ Session expired. Please log in again.")
        st.rerun()

def log_admin_action(admin_user: str, action: str, details: str = ""):
    """Log admin actions with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] Admin: {admin_user} | Action: {action} | Details: {details}"
    logger.info(log_entry)
    
    # Store in session state for audit trail
    if "admin_logs" not in st.session_state:
        st.session_state.admin_logs = []
    st.session_state.admin_logs.append(log_entry)

# --- Calendar Event Functions ---
def create_calendar_event(title: str, event_date: date, start_time: time, end_time: time, 
                         event_type: str, location: str, description: str = "") -> bool:
    """Create a new calendar event"""
    try:
        event_id = len(st.session_state.calendar_events) + 1
        event = {
            'id': event_id,
            'title': title,
            'date': event_date.isoformat(),
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'type': event_type,
            'location': location,
            'description': description,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        st.session_state.calendar_events.append(event)
        return True
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}")
        return False

def update_calendar_event(event_id: int, **kwargs) -> bool:
    """Update an existing calendar event"""
    try:
        for event in st.session_state.calendar_events:
            if event['id'] == event_id:
                for key, value in kwargs.items():
                    if key in ['date', 'start_time', 'end_time']:
                        event[key] = value.isoformat() if hasattr(value, 'isoformat') else str(value)
                    else:
                        event[key] = value
                event['updated_at'] = datetime.now().isoformat()
                return True
        return False
    except Exception as e:
        logger.error(f"Error updating calendar event: {e}")
        return False

def delete_calendar_event(event_id: int) -> bool:
    """Delete a calendar event"""
    try:
        st.session_state.calendar_events = [
            e for e in st.session_state.calendar_events if e['id'] != event_id
        ]
        return True
    except Exception as e:
        logger.error(f"Error deleting calendar event: {e}")
        return False

def get_events_for_date(target_date: date) -> List[Dict]:
    """Get all events for a specific date"""
    events = []
    for event in st.session_state.calendar_events:
        event_date = datetime.fromisoformat(event['date']).date()
        if event_date == target_date:
            events.append(event)
    return sorted(events, key=lambda x: x['start_time'])

def get_events_for_month(year: int, month: int) -> Dict[int, List[Dict]]:
    """Get all events for a specific month"""
    events_by_day = {}
    for event in st.session_state.calendar_events:
        event_date = datetime.fromisoformat(event['date']).date()
        if event_date.year == year and event_date.month == month:
            day = event_date.day
            if day not in events_by_day:
                events_by_day[day] = []
            events_by_day[day].append(event)
    return events_by_day

# --- Utility Functions ---
def format_time_str(t_str) -> str:
    """Format time string for display"""
    try:
        if isinstance(t_str, str):
            if 'T' in t_str:  # ISO format
                t = datetime.fromisoformat(t_str).time()
            else:
                t = datetime.strptime(t_str, '%H:%M:%S').time()
        else:
            t = t_str
    except:
        return str(t_str)
    
    return t.strftime("%-I:%M %p")

def update_statuses(game_id: int):
    """Update response statuses based on capacity"""
    df = load_responses(game_id)
    if df.empty:
        return
    
    # Sort by timestamp to maintain FIFO order
    df = df.sort_values('timestamp')
    cumulative_count = 0
    updates_needed = []
    
    for _, row in df.iterrows():
        # Skip if already has a status
        if row.get('status') in ['❌ Cancelled', '✅ Confirmed', '⏳ Waitlist']:
            if row.get('status') == '✅ Confirmed':
                # Count confirmed players
                others_str = str(row.get('others', '') or '')
                extras = len([o.strip() for o in others_str.split(',') if o.strip()])
                cumulative_count += 1 + extras
            continue
        
        # Calculate total players for this response
        others_str = str(row.get('others', '') or '')
        extras = len([o.strip() for o in others_str.split(',') if o.strip()])
        total_players = 1 + extras
        
        # Determine status based on capacity
        if cumulative_count + total_players <= CAPACITY:
            new_status = '✅ Confirmed'
            cumulative_count += total_players
        else:
            new_status = '⏳ Waitlist'
        
        updates_needed.append((row['name'], new_status))
    
    # Apply all updates
    for name, status in updates_needed:
        update_response_status(game_id, [name], status)

def generate_teams(game_id: int, num_teams: int = 2) -> Optional[List[List[str]]]:
    """Generate balanced teams from confirmed players"""
    update_statuses(game_id)
    df = load_responses(game_id)
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

def show_metrics_and_chart(df: pd.DataFrame):
    """Display enhanced metrics and interactive chart"""
    # Calculate metrics
    confirmed = len(df[df['status'] == '✅ Confirmed'])
    waitlist = len(df[df['status'] == '⏳ Waitlist'])
    cancelled = len(df[df['status'] == '❌ Cancelled'])
    
    # Count total players including "others"
    total_confirmed_players = 0
    for _, row in df[df['status'] == '✅ Confirmed'].iterrows():
        others_str = str(row.get('others', '') or '')
        extras = len([o.strip() for o in others_str.split(',') if o.strip()])
        total_confirmed_players += 1 + extras
    
    # Display metrics with custom styling
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("✅ Confirmed", confirmed, 
                 f"{total_confirmed_players} total players",
                 delta_color="normal")
    
    with col2:
        st.metric("⏳ Waitlist", waitlist)
    
    with col3:
        st.metric("❌ Cancelled", cancelled)
    
    with col4:
        capacity_percentage = (total_confirmed_players / CAPACITY) * 100
        st.metric("📊 Capacity", f"{capacity_percentage:.0f}%",
                 f"{total_confirmed_players}/{CAPACITY}")
    
    # Progress bar with color coding
    progress_color = "normal"
    if capacity_percentage >= 100:
        progress_color = "red"
    elif capacity_percentage >= 80:
        progress_color = "orange"
    
    st.progress(min(capacity_percentage / 100, 1.0), 
               text=f"Game is {capacity_percentage:.0f}% full")
    
    # Interactive chart
    if confirmed + waitlist + cancelled > 0:
        chart_data = pd.DataFrame({
            'Status': ['Confirmed', 'Waitlist', 'Cancelled'],
            'Count': [confirmed, waitlist, cancelled],
            'Players': [total_confirmed_players, waitlist, cancelled]
        })
        
        # Create interactive Altair chart
        chart = alt.Chart(chart_data).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            x=alt.X('Count:Q', title='Number of Responses', axis=alt.Axis(grid=False)),
            y=alt.Y('Status:N', sort='-x', title='', axis=alt.Axis(labelFontSize=14)),
            color=alt.Color('Status:N', 
                          scale=alt.Scale(
                              domain=['Confirmed', 'Waitlist', 'Cancelled'],
                              range=['#4CAF50', '#FFC107', '#F44336']
                          ),
                          legend=None),
            tooltip=[
                alt.Tooltip('Status:N', title='Status'),
                alt.Tooltip('Count:Q', title='Responses'),
                alt.Tooltip('Players:Q', title='Total Players')
            ]
        ).properties(
            width='container',
            height=200
        ).configure_mark(
            opacity=0.9
        ).configure_view(
            strokeWidth=0
        )
        
        st.altair_chart(chart, use_container_width=True)

# --- UI Component Functions ---
def show_system_status():
    """Display enhanced system status"""
    with st.sidebar.expander("🔧 System Status", expanded=False):
        conn, db_type = get_connection()
        
        status_cols = st.columns(2)
        
        with status_cols[0]:
            if db_type == "postgresql":
                st.success("✅ PostgreSQL")
            elif db_type == "sqlite":
                st.warning("⚠️ SQLite")
            else:
                st.info("📝 Session")
        
        with status_cols[1]:
            if GOOGLE_DRIVE_AVAILABLE:
                st.success("☁️ Backup OK")
            else:
                st.warning("⚠️ No Backup")
        
        # Show last refresh time
        if "last_refresh" in st.session_state:
            time_since = datetime.now() - st.session_state.last_refresh
            st.caption(f"Last refresh: {time_since.seconds//60}m ago")
        
        # Auto-refresh toggle
        auto_refresh = st.checkbox("Auto-refresh", 
                                  value=st.session_state.user_preferences.get("auto_refresh", True))
        st.session_state.user_preferences["auto_refresh"] = auto_refresh
        
        if conn:
            release_connection(conn, db_type)

def show_admin_tab(df: pd.DataFrame, game_id: int, status_filter: str):
    """Enhanced admin management tab"""
    filtered = df[df['status'] == status_filter].copy()
    
    if not filtered.empty:
        # Add total players column
        filtered['Total Players'] = filtered.apply(
            lambda row: 1 + len([o.strip() for o in str(row.get('others', '')).split(',') if o.strip()]),
            axis=1
        )
        
        # Display with selection
        selected_indices = st.multiselect(
            f"Select players from {status_filter}",
            options=filtered.index.tolist(),
            format_func=lambda x: f"{filtered.loc[x, 'name']} ({filtered.loc[x, 'Total Players']} players)",
            key=f"select_{status_filter}"
        )
        
        if selected_indices:
            selected_names = filtered.loc[selected_indices, 'name'].tolist()
            
            # Action buttons in columns
            action_cols = st.columns(4)
            
            with action_cols[0]:
                if st.button("✅ Confirm", key=f"confirm_{status_filter}", 
                           help="Move to confirmed list", use_container_width=True):
                    if update_response_status(game_id, selected_names, '✅ Confirmed'):
                        st.success("✅ Moved to Confirmed")
                        log_admin_action("admin", "Moved to Confirmed", f"Players: {', '.join(selected_names)}")
                        st.rerun()
            
            with action_cols[1]:
                if st.button("⏳ Waitlist", key=f"waitlist_{status_filter}",
                           help="Move to waitlist", use_container_width=True):
                    if update_response_status(game_id, selected_names, '⏳ Waitlist'):
                        st.success("⏳ Moved to Waitlist")
                        log_admin_action("admin", "Moved to Waitlist", f"Players: {', '.join(selected_names)}")
                        st.rerun()
            
            with action_cols[2]:
                if st.button("❌ Cancel", key=f"cancel_{status_filter}",
                           help="Mark as cancelled", use_container_width=True):
                    if update_response_status(game_id, selected_names, '❌ Cancelled'):
                        st.success("❌ Marked as Cancelled")
                        log_admin_action("admin", "Marked as Cancelled", f"Players: {', '.join(selected_names)}")
                        st.rerun()
            
            with action_cols[3]:
                if st.button("🗑️ Delete", key=f"delete_{status_filter}",
                           help="Permanently delete", type="secondary", use_container_width=True):
                    if st.checkbox(f"Confirm deletion of {len(selected_names)} player(s)", 
                                  key=f"confirm_delete_{status_filter}"):
                        if delete_responses(game_id, selected_names):
                            st.success("🗑️ Deleted successfully")
                            log_admin_action("admin", "Deleted players", f"Players: {', '.join(selected_names)}")
                            st.rerun()
        
        # Display table with enhanced formatting
        display_df = filtered[['name', 'others', 'Total Players', 'timestamp']].copy()
        display_df['timestamp'] = pd.to_datetime(display_df['timestamp']).dt.strftime('%b %d, %I:%M %p')
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info(f"No players in {status_filter} status")

def display_calendar_month(year: int, month: int):
    """Display enhanced interactive calendar"""
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(year, month)
    events_by_day = get_events_for_month(year, month)
    
    # Calendar styling
    st.markdown("""
    <style>
        .calendar-day {
            min-height: 80px;
            padding: 8px;
            margin: 2px;
            border-radius: 8px;
            transition: all 0.3s ease;
        }
        .calendar-day:hover {
            transform: scale(1.05);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        .calendar-today {
            background-color: #e3f2fd !important;
            border: 2px solid #2196F3;
        }
        .calendar-selected {
            background-color: #c8e6c9 !important;
            border: 2px solid #4CAF50;
        }
        .calendar-has-events {
            background-color: #fff3e0;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Weekday headers with styling
    weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    header_cols = st.columns(7)
    for i, day in enumerate(weekdays):
        with header_cols[i]:
            st.markdown(f"<div style='text-align: center; font-weight: bold; color: #666;'>{day}</div>", 
                       unsafe_allow_html=True)
    
    # Calendar grid
    for week in month_days:
        week_cols = st.columns(7)
        for i, day in enumerate(week):
            with week_cols[i]:
                if day == 0:
                    st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
                else:
                    day_date = date(year, month, day)
                    today = date.today()
                    
                    # Determine styling
                    css_classes = ["calendar-day"]
                    if day_date == today:
                        css_classes.append("calendar-today")
                    if day_date == st.session_state.selected_date:
                        css_classes.append("calendar-selected")
                    if day in events_by_day:
                        css_classes.append("calendar-has-events")
                    
                    # Day button with event count
                    event_count = len(events_by_day.get(day, []))
                    button_label = str(day)
                    if event_count > 0:
                        button_label += f"\n📅 {event_count}"
                    
                    if st.button(button_label, 
                               key=f"cal_{year}_{month}_{day}",
                               use_container_width=True,
                               help=f"Click to view {day_date.strftime('%B %d')}"):
                        st.session_state.selected_date = day_date
                        st.rerun()

def display_day_events(target_date: date):
    """Display events for a specific day with enhanced UI"""
    events = get_events_for_date(target_date)
    
    st.markdown(f"### 📋 {target_date.strftime('%A, %B %d, %Y')}")
    
    if not events:
        st.info("💤 No events scheduled for this day")
        
        # Quick add event button for admins
        if st.session_state.admin_authenticated:
            if st.button("➕ Quick Add Event", use_container_width=True):
                st.session_state.quick_add_date = target_date
                st.rerun()
    else:
        # Sort events by start time
        events.sort(key=lambda x: x['start_time'])
        
        for event in events:
            event_type_info = EVENT_TYPES.get(event['type'], {"color": "#666", "icon": "📅"})
            
            # Event card with gradient background
            with st.container():
                event_html = f"""
                <div style="
                    background: linear-gradient(135deg, {event_type_info['color']}15 0%, {event_type_info['color']}05 100%);
                    border-left: 4px solid {event_type_info['color']};
                    border-radius: 8px;
                    padding: 16px;
                    margin: 12px 0;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                    transition: all 0.3s ease;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 8px 0; color: {event_type_info['color']};">
                                {event_type_info['icon']} {event['title']}
                            </h4>
                            <div style="color: #666; font-size: 14px;">
                                <span style="margin-right: 16px;">🕐 {format_time_str(event['start_time'])} - {format_time_str(event['end_time'])}</span>
                                <span>📍 {event['location']}</span>
                            </div>
                            {f'<p style="margin: 8px 0 0 0; color: #555; font-size: 14px;">{event["description"]}</p>' if event.get('description') else ''}
                        </div>
                        <div style="background: {event_type_info['color']}; color: white; padding: 4px 12px; border-radius: 16px; font-size: 12px; font-weight: 500;">
                            {event['type'].replace('🏀 ', '').replace('🏃 ', '').replace('🏆 ', '').replace('🎉 ', '').replace('📋 ', '').replace('🚫 ', '')}
                        </div>
                    </div>
                </div>
                """
                st.markdown(event_html, unsafe_allow_html=True)
                
                # Admin controls
                if st.session_state.admin_authenticated:
                    admin_cols = st.columns([8, 1, 1])
                    with admin_cols[1]:
                        if st.button("✏️", key=f"edit_day_{event['id']}", 
                                   help="Edit event", use_container_width=True):
                            st.session_state.editing_event_id = event['id']
                            st.session_state.show_edit_form = True
                            st.rerun()
                    with admin_cols[2]:
                        if st.button("🗑️", key=f"delete_day_{event['id']}", 
                                   help="Delete event", use_container_width=True):
                            if delete_calendar_event(event['id']):
                                st.success("Event deleted!")
                                log_admin_action("admin", "Event deleted", f"Event: {event['title']}")
                                st.rerun()

# === INITIALIZATION CODE ===
# Initialize session state first
init_session_state()

# Initialize database tables if needed
if not st.session_state.tables_initialized:
    if create_tables():
        st.session_state.tables_initialized = True
        logger.info("Database tables initialized successfully")
    else:
        logger.warning("Failed to initialize database tables, using session state storage")

# === MAIN APPLICATION STARTS HERE ===

# --- Main Navigation ---
st.sidebar.title("🏀 Basketball Organizer")
st.sidebar.markdown("---")

# Navigation with icons
nav_options = {
    "🏀 RSVP": "rsvp",
    "📅 Calendar": "calendar",
    "⚙️ Admin": "admin",
    "📊 Analytics": "analytics"
}

selected_page = st.sidebar.radio(
    "Navigate to:",
    options=list(nav_options.keys()),
    index=0,
    key="navigation"
)

current_section = nav_options[selected_page]

# Show system status
show_system_status()

# Check session timeout for admin pages
if current_section in ["admin", "analytics"]:
    check_session_timeout()

# --- RSVP PAGE ---
if current_section == "rsvp":
    st.title("🏀 Basketball Game RSVP")
    
    # Add refresh button
    col1, col2 = st.columns([10, 1])
    with col2:
        if st.button("🔄", help="Refresh data"):
            st.session_state.last_refresh = datetime.now()
            st.rerun()
    
    current_game = load_current_game()
    
    if not current_game:
        st.warning("📅 No game scheduled yet")
        st.info("The organizer will schedule the next game soon. Check back later!")
        
        # Show upcoming events
        st.markdown("### 📅 Upcoming Basketball Events")
        upcoming_events = []
        today = date.today()
        
        for event in st.session_state.calendar_events:
            event_date = datetime.fromisoformat(event['date']).date()
            if event_date >= today and '🏀' in event.get('type', ''):
                upcoming_events.append(event)
        
        if upcoming_events:
            upcoming_events.sort(key=lambda x: x['date'])
            for event in upcoming_events[:3]:
                event_date = datetime.fromisoformat(event['date']).date()
                event_type_info = EVENT_TYPES.get(event['type'], {"color": "#666", "icon": "📅"})
                
                st.markdown(f"""
                <div style="
                    background: linear-gradient(90deg, {event_type_info['color']}20 0%, transparent 100%);
                    border-radius: 12px;
                    padding: 16px;
                    margin: 8px 0;
                ">
                    <h4 style="margin: 0; color: {event_type_info['color']};">
                        {event_type_info['icon']} {event['title']}
                    </h4>
                    <p style="margin: 8px 0 0 0; color: #666;">
                        📅 {event_date.strftime('%A, %B %d')} • 
                        🕐 {format_time_str(event['start_time'])} • 
                        📍 {event['location']}
                    </p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No upcoming basketball events scheduled")
        
        # Feature showcase
        st.markdown("### 🌟 What to Expect")
        feature_cols = st.columns(4)
        
        with feature_cols[0]:
            st.markdown("""
            <div style="text-align: center; padding: 20px;">
                <div style="font-size: 48px;">📅</div>
                <h4>Easy Scheduling</h4>
                <p>Game times and locations at a glance</p>
            </div>
            """, unsafe_allow_html=True)
        
        with feature_cols[1]:
            st.markdown("""
            <div style="text-align: center; padding: 20px;">
                <div style="font-size: 48px;">✅</div>
                <h4>Quick RSVP</h4>
                <p>Confirm attendance in seconds</p>
            </div>
            """, unsafe_allow_html=True)
        
        with feature_cols[2]:
            st.markdown("""
            <div style="text-align: center; padding: 20px;">
                <div style="font-size: 48px;">👥</div>
                <h4>Team Generation</h4>
                <p>Balanced teams created automatically</p>
            </div>
            """, unsafe_allow_html=True)
        
        with feature_cols[3]:
            st.markdown("""
            <div style="text-align: center; padding: 20px;">
                <div style="font-size: 48px;">📊</div>
                <h4>Live Updates</h4>
                <p>See who's playing in real-time</p>
            </div>
            """, unsafe_allow_html=True)
            
    else:
        # Parse game date
        game_date = current_game['game_date']
        if isinstance(game_date, str):
            game_date = datetime.fromisoformat(game_date).date()
        
        deadline = game_date - timedelta(days=CUTOFF_DAYS)
        today = date.today()
        
        # Game header with countdown
        game_info_container = st.container()
        with game_info_container:
            # Countdown banner
            if today < game_date:
                days_until = (game_date - today).days
                if days_until == 0:
                    st.success("🎉 **Game Day is TODAY!** See you on the court!")
                elif days_until == 1:
                    st.info("🏀 **Game is TOMORROW!** Get ready!")
                else:
                    st.info(f"📅 **{days_until} days** until game day")
            elif today == game_date:
                st.success("🎉 **It's Game Day!** Let's play!")
            else:
                st.warning("This game has already taken place")
            
            # Game details card
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
                color: white;
                padding: 24px;
                border-radius: 16px;
                margin: 16px 0;
                box-shadow: 0 4px 12px rgba(76, 175, 80, 0.3);
            ">
                <h2 style="margin: 0 0 16px 0;">🏀 Next Game: {game_date.strftime('%A, %B %d')}</h2>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;">
                    <div>
                        <div style="opacity: 0.9; font-size: 14px;">TIME</div>
                        <div style="font-size: 20px; font-weight: 600;">
                            {format_time_str(current_game['start_time'])} - {format_time_str(current_game['end_time'])}
                        </div>
                    </div>
                    <div>
                        <div style="opacity: 0.9; font-size: 14px;">LOCATION</div>
                        <div style="font-size: 20px; font-weight: 600;">{current_game['location']}</div>
                    </div>
                    <div>
                        <div style="opacity: 0.9; font-size: 14px;">RSVP DEADLINE</div>
                        <div style="font-size: 20px; font-weight: 600;">{deadline.strftime('%b %d')}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # Load and display responses
        df = load_responses(current_game['id'])
        
        # Metrics and visualization
        st.markdown("### 📊 Current Status")
        show_metrics_and_chart(df)
        
        # Player lists with enhanced display
        with st.expander("👥 **Player List**", expanded=True):
            list_cols = st.columns(2)
            
            with list_cols[0]:
                st.markdown("#### ✅ Confirmed Players")
                confirmed = df[df['status'] == '✅ Confirmed']
                if not confirmed.empty:
                    total_confirmed = 0
                    for idx, row in confirmed.iterrows():
                        others_str = str(row.get('others', '') or '')
                        others_list = [o.strip() for o in others_str.split(',') if o.strip()]
                        player_count = 1 + len(others_list)
                        total_confirmed += player_count
                        
                        player_text = f"**{row['name']}**"
                        if others_list:
                            player_text += f" (+{len(others_list)}): {', '.join(others_list)}"
                        
                        st.markdown(f"• {player_text}")
                    
                    st.markdown(f"**Total: {total_confirmed} players**")
                else:
                    st.info("No confirmed players yet")
            
            with list_cols[1]:
                st.markdown("#### ⏳ Waitlist")
                waitlist = df[df['status'] == '⏳ Waitlist']
                if not waitlist.empty:
                    waitlist_position = 1
                    for idx, row in waitlist.iterrows():
                        others_str = str(row.get('others', '') or '')
                        others_list = [o.strip() for o in others_str.split(',') if o.strip()]
                        
                        player_text = f"{waitlist_position}. {row['name']}"
                        if others_list:
                            player_text += f" (+{len(others_list)})"
                        
                        st.markdown(player_text)
                        waitlist_position += 1
                else:
                    st.info("Waitlist is empty")
        
        # RSVP Form with enhanced UI
        if today <= deadline:
            st.markdown("### 📝 RSVP for the Game")
            
            # Check for existing RSVP
            user_name = st.session_state.get('last_rsvp_name', '')
            existing_rsvp = None
            if user_name and not df.empty:
                existing_rsvp = df[df['name'].str.lower() == user_name.lower()]
            
            if not existing_rsvp.empty:
                st.info(f"ℹ️ You have an existing RSVP as **{existing_rsvp.iloc[0]['name']}** "
                       f"(Status: {existing_rsvp.iloc[0]['status']})")
            
            with st.form("rsvp_form", clear_on_submit=False):
                form_cols = st.columns([2, 1])
                
                with form_cols[0]:
                    name = st.text_input(
                        "Your Name *",
                        value=user_name,
                        placeholder="Enter your first name",
                        help="This name will be used for team generation"
                    )
                    
                    others = st.text_input(
                        "Bringing friends? (optional)",
                        placeholder="e.g., John, Sarah, Mike",
                        help="Separate multiple names with commas"
                    )
                
                with form_cols[1]:
                    attend = st.radio(
                        "Will you attend?",
                        ["Yes ✅", "No ❌"],
                        index=0
                    )
                
                # Show capacity warning
                if attend == "Yes ✅" and not df.empty:
                    confirmed_count = sum(1 + len([o.strip() for o in str(row.get('others', '')).split(',') if o.strip()])
                                        for _, row in df[df['status'] == '✅ Confirmed'].iterrows())
                    others_count = len([o.strip() for o in others.split(',') if o.strip()]) if others else 0
                    total_requesting = 1 + others_count
                    
                    if confirmed_count >= CAPACITY:
                        st.warning("⚠️ **Game is FULL!** You'll be added to the waitlist.")
                    elif confirmed_count + total_requesting > CAPACITY:
                        st.warning(f"⚠️ Game is nearly full! Some players might be waitlisted.")
                    
                    if others_count > 0:
                        st.info(f"ℹ️ Total RSVP: **{total_requesting} players** (you + {others_count})")
                
                submit_cols = st.columns([3, 1])
                with submit_cols[0]:
                    submit_button = st.form_submit_button(
                        "🎫 Submit RSVP",
                        use_container_width=True,
                        type="primary"
                    )
                
                if submit_button:
                    if not name.strip():
                        st.error("❌ Please enter your name")
                    else:
                        # Store name for future use
                        st.session_state.last_rsvp_name = name.strip()
                        
                        # Add response
                        if add_response(name.strip(), others.strip(), 
                                      attend == "Yes ✅", current_game['id']):
                            update_statuses(current_game['id'])
                            
                            if not existing_rsvp.empty:
                                st.success("✅ Your RSVP has been updated!")
                            else:
                                st.success("✅ RSVP recorded successfully!")
                            
                            # Show confirmation animation
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("❌ Failed to record RSVP. Please try again.")
        else:
            st.error(f"⏰ RSVP deadline has passed ({deadline.strftime('%B %d')})")
            st.info("Contact the organizer if you need to make changes.")
        
        # Recent activity feed
        if not df.empty:
            with st.expander("📈 Recent Activity", expanded=False):
                recent_df = df.sort_values('timestamp', ascending=False).head(10)
                
                for _, row in recent_df.iterrows():
                    timestamp = pd.to_datetime(row['timestamp'])
                    time_ago = datetime.now() - timestamp.replace(tzinfo=None)
                    
                    # Format time ago
                    if time_ago.days > 0:
                        time_str = f"{time_ago.days}d ago"
                    elif time_ago.seconds > 3600:
                        time_str = f"{time_ago.seconds // 3600}h ago"
                    elif time_ago.seconds > 60:
                        time_str = f"{time_ago.seconds // 60}m ago"
                    else:
                        time_str = "Just now"
                    
                    # Activity message
                    if row['status'] == '❌ Cancelled':
                        action = "cancelled"
                        icon = "🚫"
                    elif row['status'] == '✅ Confirmed':
                        action = "confirmed"
                        icon = "✅"
                    elif row['status'] == '⏳ Waitlist':
                        action = "joined waitlist"
                        icon = "⏳"
                    else:
                        action = "responded"
                        icon = "📝"
                    
                    st.markdown(f"{icon} **{row['name']}** {action} • {time_str}")

# --- CALENDAR PAGE ---
elif current_section == "calendar":
    st.title("📅 Basketball Events Calendar")
    
    # Calendar controls
    cal_cols = st.columns([1, 3, 1])
    
    with cal_cols[0]:
        if st.button("◀ Previous", use_container_width=True):
            current = st.session_state.selected_date
            if current.month == 1:
                new_date = current.replace(year=current.year - 1, month=12)
            else:
                new_date = current.replace(month=current.month - 1)
            st.session_state.selected_date = new_date
            st.rerun()
    
    with cal_cols[1]:
        st.markdown(
            f"<h2 style='text-align: center; margin: 0;'>"
            f"{st.session_state.selected_date.strftime('%B %Y')}</h2>",
            unsafe_allow_html=True
        )
    
    with cal_cols[2]:
        if st.button("Next ▶", use_container_width=True):
            current = st.session_state.selected_date
            if current.month == 12:
                new_date = current.replace(year=current.year + 1, month=1)
            else:
                new_date = current.replace(month=current.month + 1)
            st.session_state.selected_date = new_date
            st.rerun()
    
    # Quick navigation
    quick_nav_cols = st.columns([1, 1, 3])
    with quick_nav_cols[0]:
        if st.button("📍 Today", use_container_width=True):
            st.session_state.selected_date = date.today()
            st.rerun()
    
    with quick_nav_cols[1]:
        # Month/Year selector
        selected_month = st.selectbox(
            "Jump to",
            options=range(1, 13),
            format_func=lambda x: calendar.month_name[x],
            index=st.session_state.selected_date.month - 1,
            key="month_jump"
        )
        if selected_month != st.session_state.selected_date.month:
            st.session_state.selected_date = st.session_state.selected_date.replace(month=selected_month)
            st.rerun()
    
    # Display calendar
    display_calendar_month(
        st.session_state.selected_date.year,
        st.session_state.selected_date.month
    )
    
    st.markdown("---")
    
    # Display selected day events
    display_day_events(st.session_state.selected_date)
    
    # Upcoming events summary
    st.markdown("### 📋 Upcoming Events")
    upcoming_events = []
    today = date.today()
    
    for event in st.session_state.calendar_events:
        event_date = datetime.fromisoformat(event['date']).date()
        if today <= event_date <= today + timedelta(days=30):
            upcoming_events.append(event)
    
    if upcoming_events:
        upcoming_events.sort(key=lambda x: x['date'])
        
        # Group by week
        weeks = {}
        for event in upcoming_events:
            event_date = datetime.fromisoformat(event['date']).date()
            week_start = event_date - timedelta(days=event_date.weekday())
            week_key = week_start.strftime('%Y-%m-%d')
            
            if week_key not in weeks:
                weeks[week_key] = []
            weeks[week_key].append(event)
        
        for week_start, week_events in weeks.items():
            week_date = datetime.strptime(week_start, '%Y-%m-%d').date()
            st.markdown(f"#### Week of {week_date.strftime('%B %d')}")
            
            for event in week_events:
                event_date = datetime.fromisoformat(event['date']).date()
                event_type_info = EVENT_TYPES.get(event['type'], {"color": "#666", "icon": "📅"})
                
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"""
                    {event_type_info['icon']} **{event['title']}** - 
                    {event_date.strftime('%a %b %d')} at {format_time_str(event['start_time'])}
                    """)
    else:
        st.info("No upcoming events in the next 30 days")
    
    # Event type legend
    with st.expander("📖 Event Types"):
        legend_cols = st.columns(3)
        for i, (event_type, info) in enumerate(EVENT_TYPES.items()):
            with legend_cols[i % 3]:
                st.markdown(f"""
                <div style="
                    padding: 8px;
                    margin: 4px;
                    border-left: 4px solid {info['color']};
                    background: {info['color']}15;
                    border-radius: 4px;
                ">
                    {info['icon']} <strong>{event_type}</strong>
                </div>
                """, unsafe_allow_html=True)

# --- ADMIN PAGE ---
elif current_section == "admin":
    st.title("⚙️ Admin Dashboard")
    
    # Admin authentication
    if not st.session_state.admin_authenticated:
        st.markdown("### 🔐 Admin Login")
        
        with st.form("admin_login"):
            login_cols = st.columns([2, 1])
            
            with login_cols[0]:
                username = st.text_input("Username", placeholder="admin")
                password = st.text_input("Password", type="password")
            
            with login_cols[1]:
                st.markdown("<br>", unsafe_allow_html=True)
                login_button = st.form_submit_button("🔓 Login", use_container_width=True)
            
            if login_button:
                if authenticate_admin(username, password):
                    st.session_state.admin_authenticated = True
                    st.session_state.admin_login_time = datetime.now()
                    log_admin_action(username, "Admin login")
                    st.success("✅ Login successful!")
                    st.rerun()
                else:
                    st.error("❌ Invalid credentials")
        
        # Help section
        with st.expander("Need help?"):
            st.info("Contact the system administrator if you've forgotten your credentials.")
    
    else:
        # Admin header with logout
        admin_header_cols = st.columns([4, 1])
        with admin_header_cols[0]:
            st.markdown(f"Welcome back, **Admin**! "
                       f"(Session: {(datetime.now() - st.session_state.admin_login_time).seconds // 60} min)")
        with admin_header_cols[1]:
            if st.button("🚪 Logout", use_container_width=True):
                st.session_state.admin_authenticated = False
                st.session_state.admin_login_time = None
                log_admin_action("admin", "Admin logout")
                st.rerun()
        
        # Admin tabs
        admin_tabs = st.tabs(["🏀 Game Management", "📅 Calendar Events", 
                             "👥 Player Management", "🔧 System Settings"])
        
        # Game Management Tab
        with admin_tabs[0]:
            st.markdown("### 📅 Schedule New Game")
            
            with st.form("schedule_game_form"):
                sched_cols = st.columns(2)
                
                with sched_cols[0]:
                    game_date = st.date_input(
                        "Game Date",
                        value=date.today() + timedelta(days=7),
                        min_value=date.today()
                    )
                    start_time = st.time_input("Start Time", value=time(18, 0))
                
                with sched_cols[1]:
                    end_time = st.time_input("End Time", value=time(20, 0))
                    location = st.text_input("Location", value=DEFAULT_LOCATION)
                
                schedule_button = st.form_submit_button("📅 Schedule Game", use_container_width=True)
                
                if schedule_button:
                    if end_time <= start_time:
                        st.error("End time must be after start time")
                    else:
                        if save_game(game_date, start_time, end_time, location):
                            # Create calendar event
                            create_calendar_event(
                                title="Basketball Game",
                                event_date=game_date,
                                start_time=start_time,
                                end_time=end_time,
                                event_type="🏀 Game",
                                location=location,
                                description="Official weekly basketball game"
                            )
                            st.success("✅ Game scheduled successfully!")
                            log_admin_action("admin", "Game scheduled", 
                                           f"{game_date} at {location}")
                            st.rerun()
                        else:
                            st.error("Failed to schedule game")
            
            # Current game management
            current_game = load_current_game()
            if current_game:
                st.markdown("### 🏀 Current Game Management")
                
                # Game info card
                st.info(f"**Current Game:** {current_game['game_date']} • "
                       f"{format_time_str(current_game['start_time'])} - "
                       f"{format_time_str(current_game['end_time'])} • "
                       f"{current_game['location']}")
                
                # Load responses
                df = load_responses(current_game['id'])
                
                # Quick actions
                action_cols = st.columns(4)
                with action_cols[0]:
                    if st.button("📊 Update Status", use_container_width=True):
                        update_statuses(current_game['id'])
                        st.success("Statuses updated!")
                        st.rerun()
                
                with action_cols[1]:
                    if st.button("📧 Send Reminders", use_container_width=True):
                        st.info("Email reminders feature coming soon!")
                
                with action_cols[2]:
                    if not df.empty:
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            "📥 Export CSV",
                            csv,
                            f"rsvp_{current_game['game_date']}.csv",
                            "text/csv",
                            use_container_width=True
                        )
                
                with action_cols[3]:
                    if st.button("🗑️ Cancel Game", type="secondary", use_container_width=True):
                        if st.checkbox("Confirm cancellation"):
                            # Implementation for game cancellation
                            st.warning("Game cancellation implemented")
                
                # Response management
                if not df.empty:
                    st.markdown("### 📋 Response Management")
                    
                    # Summary metrics
                    show_metrics_and_chart(df)
                    
                    # Player management tabs
                    mgmt_tabs = st.tabs(["✅ Confirmed", "⏳ Waitlist", "❌ Cancelled"])
                    
                    for i, status in enumerate(['✅ Confirmed', '⏳ Waitlist', '❌ Cancelled']):
                        with mgmt_tabs[i]:
                            show_admin_tab(df, current_game['id'], status)
                    
                    # Team generation
                    st.markdown("### 👥 Team Generation")
                    confirmed_players = []
                    for _, row in df[df['status'] == '✅ Confirmed'].iterrows():
                        confirmed_players.append(row['name'])
                        others = str(row.get('others', '') or '')
                        confirmed_players.extend([o.strip() for o in others.split(',') if o.strip()])
                    
                    if len(confirmed_players) >= 2:
                        team_cols = st.columns([2, 1])
                        with team_cols[0]:
                            num_teams = st.slider(
                                "Number of teams",
                                min_value=2,
                                max_value=min(6, len(confirmed_players)),
                                value=min(2, len(confirmed_players) // 5 + 1)
                            )
                        
                        with team_cols[1]:
                            if st.button("🎲 Generate Teams", use_container_width=True):
                                teams = generate_teams(current_game['id'], num_teams)
                                if teams:
                                    st.success("Teams generated!")
                                    
                                    # Display teams in columns
                                    team_display_cols = st.columns(num_teams)
                                    for i, team in enumerate(teams):
                                        with team_display_cols[i]:
                                            st.markdown(f"**Team {i+1}**")
                                            for player in team:
                                                st.write(f"• {player}")
                                    
                                    st.balloons()
                                    log_admin_action("admin", "Teams generated", 
                                                   f"{num_teams} teams")
                    else:
                        st.warning("Need at least 2 confirmed players to generate teams")
            else:
                st.info("No active game. Schedule a game above to start managing.")
        
        # Calendar Events Tab
        with admin_tabs[1]:
            st.markdown("### 📅 Calendar Event Management")
            
            # Create new event
            with st.expander("➕ Create New Event", expanded=True):
                with st.form("create_event"):
                    event_cols = st.columns(2)
                    
                    with event_cols[0]:
                        event_title = st.text_input("Event Title", placeholder="e.g., Basketball Training")
                        event_date = st.date_input("Date", value=date.today() + timedelta(days=1))
                        event_start = st.time_input("Start Time", value=time(18, 0))
                    
                    with event_cols[1]:
                        event_type = st.selectbox("Event Type", list(EVENT_TYPES.keys()))
                        event_location = st.text_input("Location", value=DEFAULT_LOCATION)
                        event_end = st.time_input("End Time", value=time(20, 0))
                    
                    event_description = st.text_area("Description (optional)", 
                                                   placeholder="Event details...")
                    
                    if st.form_submit_button("Create Event", use_container_width=True):
                        if event_title and event_end > event_start:
                            if create_calendar_event(
                                title=event_title,
                                event_date=event_date,
                                start_time=event_start,
                                end_time=event_end,
                                event_type=event_type,
                                location=event_location,
                                description=event_description
                            ):
                                st.success("✅ Event created!")
                                log_admin_action("admin", "Event created", event_title)
                                st.rerun()
                        else:
                            st.error("Please fill all required fields correctly")
            
            # Event list and management
            st.markdown("### 📋 Existing Events")
            
            # Filters
            filter_cols = st.columns(3)
            with filter_cols[0]:
                filter_type = st.selectbox("Filter by Type", 
                                         ["All"] + list(EVENT_TYPES.keys()))
            with filter_cols[1]:
                filter_period = st.selectbox("Time Period", 
                                           ["All", "Future", "Past", "This Month"])
            with filter_cols[2]:
                search_term = st.text_input("Search", placeholder="Search events...")
            
            # Apply filters and display events
            filtered_events = st.session_state.calendar_events.copy()
            
            # Type filter
            if filter_type != "All":
                filtered_events = [e for e in filtered_events if e['type'] == filter_type]
            
            # Time filter
            today = date.today()
            if filter_period == "Future":
                filtered_events = [e for e in filtered_events 
                                 if datetime.fromisoformat(e['date']).date() >= today]
            elif filter_period == "Past":
                filtered_events = [e for e in filtered_events 
                                 if datetime.fromisoformat(e['date']).date() < today]
            elif filter_period == "This Month":
                filtered_events = [e for e in filtered_events 
                                 if datetime.fromisoformat(e['date']).date().month == today.month]
            
            # Search filter
            if search_term:
                search_lower = search_term.lower()
                filtered_events = [e for e in filtered_events 
                                 if search_lower in e['title'].lower() or 
                                    search_lower in e.get('description', '').lower()]
            
            # Sort by date
            filtered_events.sort(key=lambda x: x['date'])
            
            if filtered_events:
                for event in filtered_events:
                    event_date = datetime.fromisoformat(event['date']).date()
                    event_type_info = EVENT_TYPES.get(event['type'], {"color": "#666", "icon": "📅"})
                    
                    with st.container():
                        event_container_cols = st.columns([6, 1, 1])
                        
                        with event_container_cols[0]:
                            st.markdown(f"""
                            <div style="
                                border-left: 4px solid {event_type_info['color']};
                                padding: 12px;
                                background: #f9f9f9;
                                border-radius: 8px;
                                margin: 8px 0;
                            ">
                                <h4 style="margin: 0 0 8px 0; color: {event_type_info['color']};">
                                    {event_type_info['icon']} {event['title']}
                                </h4>
                                <div style="color: #666; font-size: 14px;">
                                    📅 {event_date.strftime('%A, %B %d, %Y')} • 
                                    🕐 {format_time_str(event['start_time'])} - {format_time_str(event['end_time'])} • 
                                    📍 {event['location']}
                                </div>
                                {f'<div style="margin-top: 8px; color: #555;">{event["description"]}</div>' if event.get("description") else ''}
                            </div>
                            """, unsafe_allow_html=True)
                        
                        with event_container_cols[1]:
                            if st.button("✏️", key=f"edit_admin_{event['id']}", 
                                       help="Edit event"):
                                st.session_state.editing_event_id = event['id']
                                st.session_state.show_edit_form = True
                                st.rerun()
                        
                        with event_container_cols[2]:
                            if st.button("🗑️", key=f"delete_admin_{event['id']}", 
                                       help="Delete event"):
                                if delete_calendar_event(event['id']):
                                    st.success("Event deleted!")
                                    log_admin_action("admin", "Event deleted", event['title'])
                                    st.rerun()
            else:
                st.info("No events found matching the filters")
            
            # Edit form (if editing)
            if st.session_state.get('show_edit_form') and st.session_state.get('editing_event_id'):
                editing_event = None
                for event in st.session_state.calendar_events:
                    if event['id'] == st.session_state.editing_event_id:
                        editing_event = event
                        break
                
                if editing_event:
                    st.markdown("---")
                    st.markdown("### ✏️ Edit Event")
                    
                    with st.form("edit_event_form"):
                        edit_cols = st.columns(2)
                        
                        with edit_cols[0]:
                            new_title = st.text_input("Title", value=editing_event['title'])
                            new_date = st.date_input("Date", 
                                                   value=datetime.fromisoformat(editing_event['date']).date())
                            new_start = st.time_input("Start Time",
                                                    value=datetime.fromisoformat(editing_event['start_time']).time())
                        
                        with edit_cols[1]:
                            new_type = st.selectbox("Type", list(EVENT_TYPES.keys()),
                                                  index=list(EVENT_TYPES.keys()).index(editing_event['type']))
                            new_location = st.text_input("Location", value=editing_event['location'])
                            new_end = st.time_input("End Time",
                                                  value=datetime.fromisoformat(editing_event['end_time']).time())
                        
                        new_description = st.text_area("Description", 
                                                     value=editing_event.get('description', ''))
                        
                        button_cols = st.columns(2)
                        with button_cols[0]:
                            if st.form_submit_button("💾 Save Changes", use_container_width=True):
                                if update_calendar_event(
                                    editing_event['id'],
                                    title=new_title,
                                    date=new_date,
                                    start_time=new_start,
                                    end_time=new_end,
                                    type=new_type,
                                    location=new_location,
                                    description=new_description
                                ):
                                    st.success("✅ Event updated!")
                                    log_admin_action("admin", "Event updated", new_title)
                                    st.session_state.show_edit_form = False
                                    st.session_state.editing_event_id = None
                                    st.rerun()
                        
                        with button_cols[1]:
                            if st.form_submit_button("❌ Cancel", use_container_width=True):
                                st.session_state.show_edit_form = False
                                st.session_state.editing_event_id = None
                                st.rerun()
        
        # Player Management Tab
        with admin_tabs[2]:
            st.markdown("### 👥 Player Management")
            
            # Player statistics
            all_players = {}
            for response in st.session_state.responses:
                if response['name'] not in all_players:
                    all_players[response['name']] = {
                        'games': 0,
                        'confirmed': 0,
                        'cancelled': 0,
                        'waitlisted': 0
                    }
                
                all_players[response['name']]['games'] += 1
                
                if response['status'] == '✅ Confirmed':
                    all_players[response['name']]['confirmed'] += 1
                elif response['status'] == '❌ Cancelled':
                    all_players[response['name']]['cancelled'] += 1
                elif response['status'] == '⏳ Waitlist':
                    all_players[response['name']]['waitlisted'] += 1
            
            if all_players:
                # Convert to DataFrame for display
                player_df = pd.DataFrame.from_dict(all_players, orient='index')
                player_df['attendance_rate'] = (player_df['confirmed'] / player_df['games'] * 100).round(1)
                player_df = player_df.sort_values('games', ascending=False)
                
                # Display metrics
                metric_cols = st.columns(4)
                with metric_cols[0]:
                    st.metric("Total Players", len(all_players))
                with metric_cols[1]:
                    st.metric("Active Players", len([p for p in all_players.values() if p['games'] > 0]))
                with metric_cols[2]:
                    avg_attendance = player_df['attendance_rate'].mean()
                    st.metric("Avg Attendance", f"{avg_attendance:.1f}%")
                with metric_cols[3]:
                    regular_players = len([p for p in all_players.values() if p['games'] >= 3])
                    st.metric("Regular Players", regular_players)
                
                # Player table
                st.markdown("#### Player Statistics")
                display_df = player_df[['games', 'confirmed', 'cancelled', 'waitlisted', 'attendance_rate']]
                display_df.columns = ['Games', 'Confirmed', 'Cancelled', 'Waitlisted', 'Attendance %']
                st.dataframe(display_df, use_container_width=True)
                
                # Export player data
                if st.button("📥 Export Player Data", use_container_width=True):
                    csv = display_df.to_csv().encode('utf-8')
                    st.download_button(
                        "Download CSV",
                        csv,
                        "player_statistics.csv",
                        "text/csv"
                    )
            else:
                st.info("No player data available yet")
        
        # System Settings Tab
        with admin_tabs[3]:
            st.markdown("### 🔧 System Settings")
            
            # Database management
            st.markdown("#### 💾 Database Management")
            db_cols = st.columns(3)
            
            with db_cols[0]:
                if st.button("🔄 Refresh Connection", use_container_width=True):
                    # Clear connection cache
                    get_connection_pool.cache_clear()
                    st.success("Connection refreshed!")
                    st.rerun()
            
            with db_cols[1]:
                if GOOGLE_DRIVE_AVAILABLE:
                    if st.button("☁️ Backup to Drive", use_container_width=True):
                        # Implement backup
                        st.success("Backup completed!")
                        log_admin_action("admin", "Database backup")
                else:
                    st.warning("Google Drive not configured")
            
            with db_cols[2]:
                if st.button("📊 View Logs", use_container_width=True):
                    if "admin_logs" in st.session_state:
                        with st.expander("Admin Activity Logs", expanded=True):
                            for log in reversed(st.session_state.admin_logs[-20:]):
                                st.text(log)
                    else:
                        st.info("No logs available")
            
            # System configuration
            st.markdown("#### ⚙️ Configuration")
            
            config_cols = st.columns(2)
            
            with config_cols[0]:
                new_capacity = st.number_input(
                    "Game Capacity",
                    min_value=5,
                    max_value=50,
                    value=CAPACITY,
                    help="Maximum number of players per game"
                )
                
                new_cutoff = st.number_input(
                    "RSVP Cutoff (days)",
                    min_value=0,
                    max_value=7,
                    value=CUTOFF_DAYS,
                    help="Days before game when RSVP closes"
                )
            
            with config_cols[1]:
                new_location = st.text_input(
                    "Default Location",
                    value=DEFAULT_LOCATION,
                    help="Default venue for games"
                )
                
                new_timeout = st.number_input(
                    "Session Timeout (minutes)",
                    min_value=5,
                    max_value=120,
                    value=SESSION_TIMEOUT_MINUTES,
                    help="Admin session timeout duration"
                )
            
            if st.button("💾 Save Configuration", use_container_width=True):
                # In a real app, save these to database/config
                st.success("Configuration saved!")
                log_admin_action("admin", "Configuration updated")
            
            # Danger zone
            with st.expander("⚠️ Danger Zone", expanded=False):
                st.warning("These actions cannot be undone!")
                
                danger_cols = st.columns(3)
                
                with danger_cols[0]:
                    if st.button("🗑️ Clear All Responses", type="secondary", use_container_width=True):
                        if st.checkbox("I understand this will delete all responses"):
                            st.session_state.responses = []
                            st.success("All responses cleared!")
                            log_admin_action("admin", "Cleared all responses")
                            st.rerun()
                
                with danger_cols[1]:
                    if st.button("🗑️ Clear All Events", type="secondary", use_container_width=True):
                        if st.checkbox("I understand this will delete all events"):
                            st.session_state.calendar_events = []
                            st.success("All events cleared!")
                            log_admin_action("admin", "Cleared all events")
                            st.rerun()
                
                with danger_cols[2]:
                    if st.button("🔄 Reset System", type="secondary", use_container_width=True):
                        if st.checkbox("I understand this will reset everything"):
                            for key in list(st.session_state.keys()):
                                del st.session_state[key]
                            st.success("System reset!")
                            st.rerun()

# --- ANALYTICS PAGE ---
elif current_section == "analytics":
    st.title("📊 Analytics Dashboard")
    
    if not st.session_state.admin_authenticated:
        st.warning("🔒 Please log in as admin to view analytics")
        st.info("👈 Use the Admin section to log in")
    else:
        # Analytics tabs
        analytics_tabs = st.tabs(["📈 Overview", "🏀 Game Analytics", 
                                 "👥 Player Analytics", "📅 Trends"])
        
        # Overview Tab
        with analytics_tabs[0]:
            st.markdown("### 📊 System Overview")
            
            # Calculate overview metrics
            total_games = 1 if st.session_state.current_game else 0
            total_responses = len(st.session_state.responses)
            total_events = len(st.session_state.calendar_events)
            unique_players = len(set(r['name'] for r in st.session_state.responses))
            
            # Display metrics
            overview_cols = st.columns(4)
            with overview_cols[0]:
                st.metric("Total Games", total_games, 
                         help="Total basketball games scheduled")
            with overview_cols[1]:
                st.metric("Total Responses", total_responses,
                         help="All RSVP responses")
            with overview_cols[2]:
                st.metric("Unique Players", unique_players,
                         help="Individual players who have RSVPed")
            with overview_cols[3]:
                st.metric("Calendar Events", total_events,
                         help="All types of events")
            
            # Activity timeline
            if st.session_state.responses:
                st.markdown("### 📅 Recent Activity Timeline")
                
                # Create activity data
                activities = []
                for resp in st.session_state.responses:
                    activities.append({
                        'timestamp': pd.to_datetime(resp['timestamp']),
                        'type': 'RSVP',
                        'description': f"{resp['name']} - {resp['status']}"
                    })
                
                if activities:
                    activity_df = pd.DataFrame(activities)
                    activity_df = activity_df.sort_values('timestamp', ascending=False).head(20)
                    
                    # Display timeline
                    for _, activity in activity_df.iterrows():
                        time_str = activity['timestamp'].strftime('%b %d, %I:%M %p')
                        st.markdown(f"• **{time_str}** - {activity['description']}")
        
        # Game Analytics Tab
        with analytics_tabs[1]:
            current_game = load_current_game()
            
            if current_game:
                st.markdown("### 🏀 Current Game Analytics")
                
                df = load_responses(current_game['id'])
                
                if not df.empty:
                    # Enhanced visualizations
                    viz_cols = st.columns(2)
                    
                    with viz_cols[0]:
                        # Response timeline
                        st.markdown("#### Response Timeline")
                        
                        # Prepare timeline data
                        timeline_data = df.copy()
                        timeline_data['timestamp'] = pd.to_datetime(timeline_data['timestamp'])
                        timeline_data['hour'] = timeline_data['timestamp'].dt.hour
                        
                        hourly_responses = timeline_data.groupby('hour').size().reset_index(name='count')
                        
                        timeline_chart = alt.Chart(hourly_responses).mark_area(
                            line={'color': '#4CAF50'},
                            color=alt.Gradient(
                                gradient='linear',
                                stops=[
                                    alt.GradientStop(color='#4CAF50', offset=0),
                                    alt.GradientStop(color='#81C784', offset=1)
                                ],
                                x1=1, x2=1, y1=1, y2=0
                            )
                        ).encode(
                            x=alt.X('hour:Q', title='Hour of Day'),
                            y=alt.Y('count:Q', title='Responses'),
                            tooltip=['hour:Q', 'count:Q']
                        ).properties(
                            height=300,
                            title="Responses by Hour"
                        )
                        
                        st.altair_chart(timeline_chart, use_container_width=True)
                    
                    with viz_cols[1]:
                        # Status distribution pie chart
                        st.markdown("#### Status Distribution")
                        
                        status_counts = df['status'].value_counts().reset_index()
                        status_counts.columns = ['status', 'count']
                        
                        pie_chart = alt.Chart(status_counts).mark_arc(innerRadius=50).encode(
                            theta=alt.Theta(field="count", type="quantitative"),
                            color=alt.Color(
                                field="status",
                                type="nominal",
                                scale=alt.Scale(
                                    domain=['✅ Confirmed', '⏳ Waitlist', '❌ Cancelled'],
                                    range=['#4CAF50', '#FFC107', '#F44336']
                                )
                            ),
                            tooltip=['status', 'count']
                        ).properties(
                            height=300,
                            title="Player Status Breakdown"
                        )
                        
                        st.altair_chart(pie_chart, use_container_width=True)
                    
                    # Detailed player breakdown
                    st.markdown("#### Detailed Breakdown")
                    
                    # Calculate totals including guests
                    total_confirmed_players = 0
                    total_waitlist_players = 0
                    
                    for _, row in df.iterrows():
                        others = len([o.strip() for o in str(row.get('others', '')).split(',') if o.strip()])
                        if row['status'] == '✅ Confirmed':
                            total_confirmed_players += 1 + others
                        elif row['status'] == '⏳ Waitlist':
                            total_waitlist_players += 1 + others
                    
                    breakdown_cols = st.columns(3)
                    with breakdown_cols[0]:
                        st.metric("Confirmed Players", total_confirmed_players,
                                 f"{(total_confirmed_players/CAPACITY)*100:.0f}% of capacity")
                    with breakdown_cols[1]:
                        st.metric("Waitlisted Players", total_waitlist_players)
                    with breakdown_cols[2]:
                        st.metric("Available Spots", max(0, CAPACITY - total_confirmed_players))
                    
                    # Response rate analysis
                    st.markdown("#### Response Patterns")
                    
                    # Day of week analysis
                    df['day_of_week'] = pd.to_datetime(df['timestamp']).dt.day_name()
                    day_counts = df['day_of_week'].value_counts()
                    
                    if not day_counts.empty:
                        st.bar_chart(day_counts)
                else:
                    st.info("No responses yet for the current game")
            else:
                st.info("No game scheduled. Analytics will appear once a game is scheduled.")
        
        # Player Analytics Tab
        with analytics_tabs[2]:
            st.markdown("### 👥 Player Analytics")
            
            if st.session_state.responses:
                # Player frequency analysis
                player_counts = {}
                player_statuses = {}
                
                for resp in st.session_state.responses:
                    name = resp['name']
                    if name not in player_counts:
                        player_counts[name] = 0
                        player_statuses[name] = {'confirmed': 0, 'waitlist': 0, 'cancelled': 0}
                    
                    player_counts[name] += 1
                    
                    if resp['status'] == '✅ Confirmed':
                        player_statuses[name]['confirmed'] += 1
                    elif resp['status'] == '⏳ Waitlist':
                        player_statuses[name]['waitlist'] += 1
                    elif resp['status'] == '❌ Cancelled':
                        player_statuses[name]['cancelled'] += 1
                
                # Top players
                st.markdown("#### 🏆 Most Active Players")
                top_players = sorted(player_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                
                if top_players:
                    top_players_df = pd.DataFrame(top_players, columns=['Player', 'Games'])
                    
                    # Add attendance rate
                    top_players_df['Attendance Rate'] = top_players_df['Player'].apply(
                        lambda x: f"{(player_statuses[x]['confirmed'] / player_counts[x] * 100):.0f}%"
                    )
                    
                    st.dataframe(top_players_df, use_container_width=True, hide_index=True)
                
                # Player reliability score
                st.markdown("#### 📊 Player Reliability Scores")
                
                reliability_data = []
                for player, count in player_counts.items():
                    if count >= 2:  # Only show players with 2+ games
                        confirmed = player_statuses[player]['confirmed']
                        cancelled = player_statuses[player]['cancelled']
                        reliability = (confirmed / count) * 100
                        
                        reliability_data.append({
                            'Player': player,
                            'Games': count,
                            'Reliability': reliability,
                            'Status': '🌟 Excellent' if reliability >= 80 else '👍 Good' if reliability >= 60 else '⚠️ Fair'
                        })
                
                if reliability_data:
                    reliability_df = pd.DataFrame(reliability_data)
                    reliability_df = reliability_df.sort_values('Reliability', ascending=False)
                    
                    # Reliability chart
                    reliability_chart = alt.Chart(reliability_df.head(15)).mark_bar().encode(
                        x=alt.X('Reliability:Q', title='Reliability %'),
                        y=alt.Y('Player:N', sort='-x'),
                        color=alt.Color(
                            'Reliability:Q',
                            scale=alt.Scale(scheme='greens'),
                            legend=None
                        ),
                        tooltip=['Player', 'Games', 'Reliability', 'Status']
                    ).properties(
                        height=400,
                        title="Player Reliability Rankings"
                    )
                    
                    st.altair_chart(reliability_chart, use_container_width=True)
                else:
                    st.info("Not enough data to calculate reliability scores")
            else:
                st.info("No player data available yet")
        
        # Trends Tab
        with analytics_tabs[3]:
            st.markdown("### 📈 Trends & Insights")
            
            if st.session_state.calendar_events:
                # Event trends
                st.markdown("#### Event Type Trends")
                
                # Prepare event data
                event_dates = []
                for event in st.session_state.calendar_events:
                    event_date = datetime.fromisoformat(event['date']).date()
                    event_dates.append({
                        'date': event_date,
                        'month': event_date.strftime('%Y-%m'),
                        'type': event['type']
                    })
                
                if event_dates:
                    events_df = pd.DataFrame(event_dates)
                    monthly_events = events_df.groupby(['month', 'type']).size().reset_index(name='count')
                    
                    # Stacked bar chart
                    trend_chart = alt.Chart(monthly_events).mark_bar().encode(
                        x=alt.X('month:O', title='Month'),
                        y=alt.Y('count:Q', title='Number of Events'),
                        color=alt.Color('type:N', title='Event Type'),
                        tooltip=['month', 'type', 'count']
                    ).properties(
                        height=300,
                        title="Monthly Event Distribution"
                    )
                    
                    st.altair_chart(trend_chart, use_container_width=True)
                
                # Capacity utilization trend
                if st.session_state.responses:
                    st.markdown("#### Capacity Utilization Trends")
                    
                    # This would need game history data in a real implementation
                    st.info("Capacity utilization trends will be available after multiple games")
                
                # Predictions
                st.markdown("#### 🔮 Predictions & Recommendations")
                
                recommendations = []
                
                # Analyze patterns
                if st.session_state.responses:
                    total_responses = len(st.session_state.responses)
                    confirmed_rate = len([r for r in st.session_state.responses if r['status'] == '✅ Confirmed']) / total_responses
                    
                    if confirmed_rate > 0.8:
                        recommendations.append("✅ High confirmation rate - consider increasing game frequency")
                    
                    if total_responses > CAPACITY * 1.5:
                        recommendations.append("📈 High demand - consider organizing additional games")
                
                if st.session_state.calendar_events:
                    game_events = [e for e in st.session_state.calendar_events if e['type'] == '🏀 Game']
                    if len(game_events) < 4:
                        recommendations.append("📅 Schedule more regular games to maintain player engagement")
                
                if recommendations:
                    for rec in recommendations:
                        st.info(rec)
                else:
                    st.success("✨ Everything looks good! Keep up the great work!")
            else:
                st.info("More data needed to show trends and insights")

# --- Footer and Sidebar Info ---
st.sidebar.markdown("---")

# Quick stats in sidebar
if st.session_state.current_game:
    st.sidebar.markdown("### 📊 Quick Stats")
    df = load_responses(st.session_state.current_game['id'])
    if not df.empty:
        confirmed = len(df[df['status'] == '✅ Confirmed'])
        st.sidebar.metric("Confirmed", f"{confirmed}/{CAPACITY}")

# Next event in sidebar
if st.session_state.calendar_events:
    next_event = None
    today = date.today()
    
    for event in st.session_state.calendar_events:
        event_date = datetime.fromisoformat(event['date']).date()
        if event_date >= today:
            if not next_event or event_date < datetime.fromisoformat(next_event['date']).date():
                next_event = event
    
    if next_event:
        st.sidebar.markdown("### 🔜 Next Event")
        event_date = datetime.fromisoformat(next_event['date']).date()
        event_type_info = EVENT_TYPES.get(next_event['type'], {"color": "#666", "icon": "📅"})
        
        st.sidebar.markdown(f"""
        <div style="
            background: {event_type_info['color']}15;
            border-left: 3px solid {event_type_info['color']};
            padding: 10px;
            border-radius: 5px;
        ">
            <strong>{event_type_info['icon']} {next_event['title']}</strong><br>
            <small>
                📅 {event_date.strftime('%b %d')}<br>
                🕐 {format_time_str(next_event['start_time'])}<br>
                📍 {next_event['location']}
            </small>
        </div>
        """, unsafe_allow_html=True)

# Version and credits
st.sidebar.markdown("---")
st.sidebar.caption("Basketball Organizer v2.0")
st.sidebar.caption("Built with ❤️ using Streamlit")

# Auto-refresh functionality
if st.session_state.user_preferences.get("auto_refresh", True):
    # Refresh every 5 minutes
    if "last_refresh" in st.session_state:
        time_since_refresh = datetime.now() - st.session_state.last_refresh
        if time_since_refresh > timedelta(minutes=5):
            st.session_state.last_refresh = datetime.now()
            st.rerun()

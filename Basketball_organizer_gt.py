import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, time, timedelta
import random
import altair as alt
import json
import logging
from typing import Optional, Dict, List, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize availability flags
DB_AVAILABLE = False
SQLITE_AVAILABLE = False
BCRYPT_AVAILABLE = False
GOOGLE_DRIVE_AVAILABLE = False

# Try to import PostgreSQL driver with fallbacks
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DB_AVAILABLE = True
    logger.info("PostgreSQL driver loaded successfully")
except ImportError as e:
    logger.warning(f"PostgreSQL driver not available: {e}")
    # Try SQLite fallback
    try:
        import sqlite3
        SQLITE_AVAILABLE = True
        logger.info("SQLite available as fallback")
    except ImportError:
        logger.error("No database drivers available")

# Try to import bcrypt with fallback
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
    logger.info("bcrypt available")
except ImportError:
    logger.warning("bcrypt not available, using basic password comparison")

# Try to import Google Drive dependencies
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    import io
    GOOGLE_DRIVE_AVAILABLE = True
    logger.info("Google Drive integration available")
except ImportError as e:
    logger.warning(f"Google Drive integration not available: {e}")

# --- Constants ---
CAPACITY = int(os.getenv('GAME_CAPACITY', '15'))
DEFAULT_LOCATION = "Main Court"
CUTOFF_DAYS = int(os.getenv('RSVP_CUTOFF_DAYS', '1'))
SESSION_TIMEOUT_MINUTES = 30

# Data storage directory for fallback
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR)
    except:
        pass  # Might not have write permissions in cloud

# --- Page Config ---
st.set_page_config(page_title="🏀 Basketball Organiser", layout="wide")

# Initialize session state
if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False
if "admin_login_time" not in st.session_state:
    st.session_state.admin_login_time = None
if "use_fallback_storage" not in st.session_state:
    st.session_state.use_fallback_storage = True
if "current_game" not in st.session_state:
    st.session_state.current_game = None
if "responses" not in st.session_state:
    st.session_state.responses = []

# --- Fallback File Storage Functions ---
def save_json(filename: str, data: Any) -> bool:
    """Save data to JSON file"""
    try:
        filepath = os.path.join(DATA_DIR, filename)
        with open(filepath, 'w') as f:
            json.dump(data, f, default=str, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")
        return False

def load_json(filename: str) -> Any:
    """Load data from JSON file"""
    try:
        filepath = os.path.join(DATA_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
    return {}

# --- Database Configuration ---
@st.cache_resource
def init_connection():
    """Initialize database connection with fallbacks"""
    # Try PostgreSQL first if available and configured
    if DB_AVAILABLE:
        try:
            # Check if database secrets are available
            if "database" in st.secrets:
                conn = psycopg2.connect(
                    host=st.secrets["database"]["host"],
                    database=st.secrets["database"]["dbname"],
                    user=st.secrets["database"]["user"],
                    password=st.secrets["database"]["password"],
                    port=st.secrets["database"]["port"],
                    connect_timeout=10  # Add timeout
                )
                logger.info("PostgreSQL connection established")
                return conn, "postgresql"
            else:
                logger.warning("Database secrets not configured")
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
    
    # Try SQLite fallback if available
    if SQLITE_AVAILABLE:
        try:
            conn = sqlite3.connect(':memory:', check_same_thread=False)  # Use in-memory DB
            logger.info("SQLite in-memory connection established")
            return conn, "sqlite"
        except Exception as e:
            logger.error(f"SQLite connection failed: {e}")
    
    # No database available - use session state
    logger.warning("No database available, using session state storage")
    return None, "session"

def create_tables():
    """Create necessary database tables with fallback support"""
    conn_info = init_connection()
    if not conn_info[0]:
        # No database - use session state
        logger.info("Using session state for data storage")
        return True
    
    conn, db_type = conn_info
    
    if db_type == "session":
        return True
    
    try:
        cur = conn.cursor()
        
        if db_type == "postgresql":
            # PostgreSQL specific SQL
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
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS responses (
                    id SERIAL PRIMARY KEY,
                    game_id INTEGER REFERENCES games(id),
                    name VARCHAR(255) NOT NULL,
                    others TEXT,
                    status VARCHAR(50) DEFAULT '',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)
            
        else:  # SQLite
            cur.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_date DATE NOT NULL,
                    start_time TIME NOT NULL,
                    end_time TIME NOT NULL,
                    location TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
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
                    FOREIGN KEY (game_id) REFERENCES games(id)
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and db_type != "session":
            conn.close()

# --- Session State Functions (Fallback) ---
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
        'id': len(st.session_state.responses) + 1,
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

# --- Authentication Functions ---
def hash_password(password: str) -> str:
    """Hash password using bcrypt or fallback"""
    if BCRYPT_AVAILABLE:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    else:
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    if BCRYPT_AVAILABLE:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    else:
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest() == hashed

def authenticate_admin(username: str, password: str) -> bool:
    """Authenticate admin user - simplified for demo"""
    # Simple authentication for now
    admin_password = st.secrets.get["ADMIN_PASSWORD"]
    return username == "admin" and password == admin_password

# --- Main Database Functions with Fallbacks ---
def save_game(game_date, start_time, end_time, location) -> bool:
    """Save game with fallback to session state"""
    conn_info = init_connection()
    if not conn_info[0] or conn_info[1] == "session":
        return save_game_session(game_date, start_time, end_time, location)
    
    conn, db_type = conn_info
    
    try:
        cur = conn.cursor()
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
            """, (game_date.isoformat(), start_time.isoformat(), end_time.isoformat(), location))
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error saving game: {e}")
        return False
    finally:
        conn.close()

def load_current_game() -> Optional[Dict]:
    """Load current game with fallback"""
    conn_info = init_connection()
    if not conn_info[0] or conn_info[1] == "session":
        return load_current_game_session()
    
    conn, db_type = conn_info
    
    try:
        if db_type == "postgresql":
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM games WHERE is_active = TRUE ORDER BY created_at DESC LIMIT 1")
        else:  # SQLite
            cur = conn.cursor()
            cur.row_factory = sqlite3.Row
            cur.execute("SELECT * FROM games WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1")
        
        result = cur.fetchone()
        cur.close()
        return dict(result) if result else None
    except Exception as e:
        logger.error(f"Error loading game: {e}")
        return None
    finally:
        conn.close()

def add_response(name: str, others: str, attend: bool, game_id: int) -> bool:
    """Add response with fallback"""
    conn_info = init_connection()
    if not conn_info[0] or conn_info[1] == "session":
        return add_response_session(name, others, attend, game_id)
    
    conn, db_type = conn_info
    
    try:
        cur = conn.cursor()
        status = '❌ Cancelled' if not attend else ''
        
        if db_type == "postgresql":
            cur.execute("SELECT id FROM responses WHERE name = %s AND game_id = %s", (name, game_id))
            existing = cur.fetchone()
            
            if existing:
                cur.execute("""
                    UPDATE responses 
                    SET others = %s, status = %s, updated_at = %s
                    WHERE id = %s
                """, (others, status, datetime.now(), existing[0]))
            else:
                cur.execute("""
                    INSERT INTO responses (game_id, name, others, status)
                    VALUES (%s, %s, %s, %s)
                """, (game_id, name, others, status))
        else:  # SQLite
            cur.execute("SELECT id FROM responses WHERE name = ? AND game_id = ?", (name, game_id))
            existing = cur.fetchone()
            
            if existing:
                cur.execute("""
                    UPDATE responses 
                    SET others = ?, status = ?, updated_at = ?
                    WHERE id = ?
                """, (others, status, datetime.now().isoformat(), existing[0]))
            else:
                cur.execute("""
                    INSERT INTO responses (game_id, name, others, status)
                    VALUES (?, ?, ?, ?)
                """, (game_id, name, others, status))
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error adding response: {e}")
        return False
    finally:
        conn.close()

def load_responses(game_id: int) -> pd.DataFrame:
    """Load responses with fallback"""
    conn_info = init_connection()
    if not conn_info[0] or conn_info[1] == "session":
        return load_responses_session(game_id)
    
    conn, db_type = conn_info
    
    try:
        if db_type == "postgresql":
            query = """
                SELECT name, others, status, timestamp, updated_at
                FROM responses 
                WHERE game_id = %s 
                ORDER BY timestamp ASC
            """
            df = pd.read_sql_query(query, conn, params=(game_id,))
        else:  # SQLite
            query = """
                SELECT name, others, status, timestamp, updated_at
                FROM responses 
                WHERE game_id = ? 
                ORDER BY timestamp ASC
            """
            df = pd.read_sql_query(query, conn, params=(game_id,))
        
        return df
    except Exception as e:
        logger.error(f"Error loading responses: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

# --- Utility Functions ---
def format_time_str(t_str) -> str:
    """Format time string for display"""
    try:
        if isinstance(t_str, str):
            t = datetime.fromisoformat(t_str).time()
        else:
            t = t_str
    except:
        parts = str(t_str).split(':')
        t = time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    
    h, m = t.hour, t.minute
    ampm = 'am' if h < 12 else 'pm'
    hr = h % 12 or 12
    if h == 12 and m == 0:
        return '12 noon'
    if m == 0:
        return f"{hr} {ampm}"
    return f"{hr}:{m:02d} {ampm}"

def update_statuses(game_id: int):
    """Update response statuses based on capacity"""
    df = load_responses(game_id)
    if df.empty:
        return
    
    df = df.sort_values('timestamp')
    cum = 0
    
    for idx, row in df.iterrows():
        if row['status'] in ['❌ Cancelled', '✅ Confirmed', '⏳ Waitlist']:
            continue
        
        others_str = str(row.get('others', '') or '')
        extras = len([o.strip() for o in others_str.split(',') if o.strip()])
        parts = 1 + extras
        
        if cum + parts <= CAPACITY:
            new_status = '✅ Confirmed'
            cum += parts
        else:
            new_status = '⏳ Waitlist'
        
        # Update status in session state
        for resp in st.session_state.responses:
            if resp['name'] == row['name'] and resp['game_id'] == game_id:
                resp['status'] = new_status
                break

def generate_teams(game_id: int, num_teams: Optional[int] = None) -> Optional[List[List[str]]]:
    """Generate teams from confirmed players"""
    update_statuses(game_id)
    df = load_responses(game_id)
    confirmed = df[df['status'] == '✅ Confirmed']
    
    players = []
    for _, row in confirmed.iterrows():
        players.append(row['name'])
        others_str = str(row.get('others', '') or '')
        for other in others_str.split(','):
            if other.strip():
                players.append(other.strip())
    
    if len(players) < 2:
        return None
    
    if not num_teams:
        num_teams = 2 if len(players) <= 10 else (len(players) + 2) // 3
    
    num_teams = max(2, min(num_teams, len(players)))
    random.shuffle(players)
    
    teams = [[] for _ in range(num_teams)]
    for i, player in enumerate(players):
        teams[i % num_teams].append(player)
    
    return teams

def show_metrics_and_chart(df: pd.DataFrame):
    """Display metrics and chart for responses"""
    conf = len(df[df['status'] == '✅ Confirmed'])
    wait = len(df[df['status'] == '⏳ Waitlist'])
    canc = len(df[df['status'] == '❌ Cancelled'])
    
    col1, col2, col3 = st.columns(3)
    col1.metric("✅ Confirmed", conf)
    col2.metric("⏳ Waitlist", wait)
    col3.metric("❌ Cancelled", canc)
    
    st.progress(min(conf / CAPACITY, 1.0), text=f"{conf}/{CAPACITY} confirmed")
    
    if conf + wait + canc > 0:  # Only show chart if there's data
        chart_data = pd.DataFrame({
            'Status': ['Confirmed', 'Waitlist', 'Cancelled'],
            'Count': [conf, wait, canc]
        })
        
        color_map = {'Confirmed': '#4CAF50', 'Waitlist': '#FFC107', 'Cancelled': '#F44336'}
        chart = alt.Chart(chart_data).mark_bar().encode(
            y=alt.Y('Status:N', sort='-x', title=''),
            x=alt.X('Count:Q', title='Players'),
            color=alt.Color('Status:N', 
                           scale=alt.Scale(domain=list(color_map.keys()), 
                                         range=list(color_map.values()))),
            tooltip=['Status:N', 'Count:Q']
        ).properties(width=500, height=200)
        
        st.altair_chart(chart, use_container_width=True)

def show_system_status():
    """Display system status"""
    with st.sidebar.expander("🔧 System Status"):
        st.markdown("**Database:**")
        conn_info = init_connection()
        if conn_info[0] and conn_info[1] == "postgresql":
            st.success("✅ PostgreSQL Connected")
        elif conn_info[0] and conn_info[1] == "sqlite":
            st.warning("⚠️ SQLite Mode")
        else:
            st.info("📝 Session Storage Mode")
        
        st.markdown("**Security:**")
        if BCRYPT_AVAILABLE:
            st.success("✅ Secure Hashing")
        else:
            st.warning("⚠️ Basic Hashing")
        
        st.markdown("**Backup:**")
        if GOOGLE_DRIVE_AVAILABLE:
            st.success("✅ Google Drive Ready")
        else:
            st.warning("⚠️ No Backup")

# --- Initialize System ---
try:
    if create_tables():
        logger.info("System initialized successfully")
    else:
        st.warning("Using fallback storage mode")
except Exception as e:
    logger.error(f"Initialization error: {e}")
    st.warning("Using session storage mode due to initialization issues")

# --- Main Application ---
st.sidebar.markdown("# 📜 Menu")
section = st.sidebar.selectbox("Navigate to", ["🏀 RSVP", "⚙️ Admin"])

show_system_status()

# --- ADMIN PAGE ---
if section == '⚙️ Admin':
    st.title(":gear: Admin Dashboard")
    
    if not st.session_state.admin_authenticated:
        st.sidebar.markdown("## Admin Login 🔒")
        username = st.sidebar.text_input("Username", value="admin")
        password = st.sidebar.text_input("Password", type="password")
        
        if st.sidebar.button("Login"):
            if authenticate_admin(username, password):
                st.session_state.admin_authenticated = True
                st.session_state.admin_login_time = datetime.now()
                st.success("Logged in successfully!")
                st.rerun()
            else:
                st.sidebar.error("Invalid credentials")
    else:
        # Game scheduling
        st.subheader(":calendar: Schedule Game")
        with st.form("schedule_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                game_date = st.date_input("Game Date", date.today() + timedelta(days=1))
                start_time = st.time_input("Start Time", value=time(10))
            with col2:
                end_time = st.time_input("End Time", value=time(12))
                location = st.text_input("Location", DEFAULT_LOCATION)
            
            if st.form_submit_button("Save Schedule"):
                if save_game(game_date, start_time, end_time, location):
                    st.success("Schedule saved!")
                    st.rerun()
                else:
                    st.error("Failed to save schedule")

        # Show current game
        current_game = load_current_game()
        if current_game:
            st.markdown(f"**Current Game:** {current_game['game_date']} — "
                       f"**{format_time_str(current_game['start_time'])} to {format_time_str(current_game['end_time'])}** "
                       f"@ **{current_game['location']}**")
            
            df = load_responses(current_game['id'])
            st.subheader(":clipboard: RSVP Overview")
            show_metrics_and_chart(df)
            
            # Team generation
            confirmed_df = df[df['status'] == '✅ Confirmed']
            conf_count = len(confirmed_df)
            if conf_count >= 2:
                st.subheader("👥 Generate Teams")
                suggested_teams = min(2 if conf_count <= 10 else (conf_count + 2)//3, conf_count)
                num_teams_input = st.number_input("Number of teams", 
                                                min_value=2, 
                                                max_value=conf_count, 
                                                value=suggested_teams)
                
                if st.button("Generate Teams"):
                    teams = generate_teams(current_game['id'], num_teams_input)
                    if teams:
                        st.markdown("### 🏆 Generated Teams:")
                        for i, team in enumerate(teams, 1):
                            st.markdown(f"**Team {i}:** {', '.join(team)}")
                        st.balloons()
                    else:
                        st.warning("Not enough players.")
        
        if st.button("🚪 Logout"):
            st.session_state.admin_authenticated = False
            st.rerun()

# --- RSVP PAGE ---
else:
    st.title(":basketball: RSVP & Basketball Game Details")
    
    current_game = load_current_game()
    if not current_game:
        st.warning("📅 No game scheduled yet.")
        st.info("The organizer will schedule the next game soon. Check back later!")
    else:
        game_date = current_game['game_date']
        if isinstance(game_date, str):
            try:
                game_date = datetime.fromisoformat(game_date).date()
            except:
                game_date = datetime.strptime(game_date, '%Y-%m-%d').date()
        
        deadline = game_date - timedelta(days=CUTOFF_DAYS)
        today = date.today()
        
        st.markdown(f"### 🏀 Next Game: **{game_date}**")
        st.markdown(f"**Time:** {format_time_str(current_game['start_time'])} to {format_time_str(current_game['end_time'])}")
        st.markdown(f"**Location:** {current_game['location']}")
        
        df = load_responses(current_game['id'])
        show_metrics_and_chart(df)
        
        # RSVP Form
        if today <= deadline:
            st.info(f"🕒 RSVP is open until **{deadline}**")
            
            with st.form("rsvp_form"):
                st.markdown("### 📝 Your RSVP")
                name = st.text_input("Your First Name", placeholder="Enter your name")
                attend = st.select_slider("Will you attend?", ["No ❌", "Yes ✅"], value="Yes ✅")
                others = st.text_input("Additional Players (comma-separated)", 
                                     placeholder="e.g., John, Sarah, Mike")
                
                if st.form_submit_button("🎫 Submit RSVP"):
                    if not name.strip():
                        st.error("❌ Please enter your name.")
                    else:
                        if add_response(name.strip(), others.strip(), 
                                      attend == "Yes ✅", current_game['id']):
                            update_statuses(current_game['id'])
                            st.success("✅ RSVP recorded successfully!")
                            st.rerun()
                        else:
                            st.error("❌ Failed to record RSVP. Please try again.")
        else:
            st.error(f"⏰ RSVP closed on {deadline}")

st.sidebar.markdown("---")
st.sidebar.markdown("🏀 **Basketball Organizer**")
st.sidebar.markdown("Built with Streamlit")

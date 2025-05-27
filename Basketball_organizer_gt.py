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
except ImportError as e:
    logger.warning(f"Google Drive integration not available: {e}")

# --- Constants ---
CAPACITY = int(os.getenv('GAME_CAPACITY', '15'))
DEFAULT_LOCATION = "Main Court"
CUTOFF_DAYS = int(os.getenv('RSVP_CUTOFF_DAYS', '1'))
SESSION_TIMEOUT_MINUTES = 30

# --- Page Config ---
st.set_page_config(page_title="🏀 Basketball Organiser", layout="wide")

# Initialize session state
if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False
if "admin_login_time" not in st.session_state:
    st.session_state.admin_login_time = None
if "current_game" not in st.session_state:
    st.session_state.current_game = None
if "responses" not in st.session_state:
    st.session_state.responses = []

# --- Authentication Functions ---
def authenticate_admin(username: str, password: str) -> bool:
    """Simple authentication using secrets.toml directly"""
    try:
        # Get admin password from secrets - FIX: correct way to access
        admin_password = st.secrets.get("admin_password", None)
        
        if admin_password is None:
            st.sidebar.error("❌ admin_password not found in secrets!")
            st.sidebar.write(f"Available secrets: {list(st.secrets.keys())}")
            return False
        
        # Clean both inputs
        clean_stored = str(admin_password).strip().strip('"').strip("'")
        clean_input_password = str(password).strip()
        clean_input_username = str(username).strip().lower()
        
        # Simple comparison
        username_match = clean_input_username == "admin"
        password_match = clean_input_password == clean_stored
        
        return username_match and password_match
        
    except Exception as e:
        st.sidebar.error(f"Authentication error: {e}")
        return False

def check_session_timeout():
    """Check if admin session has timed out"""
    if (st.session_state.admin_authenticated and 
        st.session_state.admin_login_time and
        datetime.now() - st.session_state.admin_login_time > timedelta(minutes=SESSION_TIMEOUT_MINUTES)):
        st.session_state.admin_authenticated = False
        st.session_state.admin_login_time = None
        st.warning("Session expired. Please log in again.")
        st.rerun()

def log_admin_action(admin_user: str, action: str, details: str = ""):
    """Log admin actions (simplified)"""
    logger.info(f"Admin Action - User: {admin_user}, Action: {action}, Details: {details}")

# --- Database Configuration ---
# CRITICAL FIX: Remove @st.cache_resource - this was causing the connection pooling issue
def get_connection():
    """Get a new database connection - DO NOT CACHE THIS"""
    if DB_AVAILABLE and "database" in st.secrets:
        try:
            conn = psycopg2.connect(
                host=st.secrets["database"]["host"],
                database=st.secrets["database"]["dbname"],
                user=st.secrets["database"]["user"],
                password=st.secrets["database"]["password"],
                port=st.secrets["database"]["port"],
                connect_timeout=10
            )
            return conn, "postgresql"
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
    
    if SQLITE_AVAILABLE:
        try:
            # Use a file-based SQLite database instead of in-memory for persistence
            conn = sqlite3.connect('basketball.db', check_same_thread=False)
            return conn, "sqlite"
        except Exception as e:
            logger.error(f"SQLite connection failed: {e}")
    
    return None, "session"

def init_connection():
    """Initialize connection info (for compatibility)"""
    return get_connection()

def create_tables():
    """Create necessary database tables with proper connection handling"""
    conn, db_type = get_connection()
    if not conn or db_type == "session":
        logger.info("Using session state for data storage")
        return True
    
    try:
        cur = conn.cursor()
        
        if db_type == "postgresql":
            # PostgreSQL tables
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
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
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

def update_response_status_session(game_id, names, new_status):
    """Update response status in session state"""
    for resp in st.session_state.responses:
        if resp.get('game_id') == game_id and resp.get('name') in names:
            resp['status'] = new_status
            resp['updated_at'] = datetime.now().isoformat()
    return True

def delete_responses_session(game_id, names):
    """Delete responses from session state"""
    st.session_state.responses = [
        resp for resp in st.session_state.responses 
        if not (resp.get('game_id') == game_id and resp.get('name') in names)
    ]
    return True

# --- Main Database Functions with Fallbacks ---
def save_game(game_date, start_time, end_time, location) -> bool:
    """Save game with fallback to session state"""
    conn, db_type = get_connection()
    if not conn or db_type == "session":
        return save_game_session(game_date, start_time, end_time, location)
    
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
        logger.info(f"Game saved successfully: {game_date} at {location}")
        return True
    except Exception as e:
        logger.error(f"Error saving game: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def load_current_game() -> Optional[Dict]:
    """Load current game with fallback"""
    conn, db_type = get_connection()
    if not conn or db_type == "session":
        return load_current_game_session()
    
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
        if conn:
            conn.close()

def add_response(name: str, others: str, attend: bool, game_id: int) -> bool:
    """Add response with fallback"""
    conn, db_type = get_connection()
    if not conn or db_type == "session":
        return add_response_session(name, others, attend, game_id)
    
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
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def load_responses(game_id: int) -> pd.DataFrame:
    """Load responses with fallback"""
    conn, db_type = get_connection()
    if not conn or db_type == "session":
        return load_responses_session(game_id)
    
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
        if conn:
            conn.close()

def update_response_status(game_id: int, names: List[str], new_status: str) -> bool:
    """Update response status with fallback"""
    conn, db_type = get_connection()
    if not conn or db_type == "session":
        return update_response_status_session(game_id, names, new_status)
    
    try:
        cur = conn.cursor()
        
        if db_type == "postgresql":
            cur.execute("""
                UPDATE responses 
                SET status = %s, updated_at = %s
                WHERE game_id = %s AND name = ANY(%s)
            """, (new_status, datetime.now(), game_id, names))
        else:  # SQLite
            for name in names:
                cur.execute("""
                    UPDATE responses 
                    SET status = ?, updated_at = ?
                    WHERE game_id = ? AND name = ?
                """, (new_status, datetime.now().isoformat(), game_id, name))
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error updating response status: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def delete_responses(game_id: int, names: List[str]) -> bool:
    """Delete responses with fallback"""
    conn, db_type = get_connection()
    if not conn or db_type == "session":
        return delete_responses_session(game_id, names)
    
    try:
        cur = conn.cursor()
        
        if db_type == "postgresql":
            cur.execute("""
                DELETE FROM responses 
                WHERE game_id = %s AND name = ANY(%s)
            """, (game_id, names))
        else:  # SQLite
            for name in names:
                cur.execute("""
                    DELETE FROM responses 
                    WHERE game_id = ? AND name = ?
                """, (game_id, name))
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error deleting responses: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# --- Google Drive Integration ---
class GoogleDriveBackup:
    def __init__(self):
        self.service = None
        if GOOGLE_DRIVE_AVAILABLE and "google_drive" in st.secrets:
            self.folder_id = st.secrets["google_drive"].get("backup_folder_id")
        else:
            self.folder_id = None
    
    def authenticate(self):
        """Authenticate with Google Drive API"""
        if not GOOGLE_DRIVE_AVAILABLE:
            return False
        
        try:
            credentials_info = st.secrets["google_drive"]["service_account"]
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/drive.file']
            )
            
            self.service = build('drive', 'v3', credentials=credentials)
            return True
        except Exception as e:
            logger.error(f"Google Drive authentication failed: {e}")
            return False
    
    def backup_database(self):
        """Create backup of database and upload to Google Drive"""
        if not self.authenticate():
            return False
        
        try:
            backup_data = self.export_database_data()
            backup_content = json.dumps(backup_data, indent=2, default=str)
            backup_file = io.BytesIO(backup_content.encode())
            
            filename = f"basketball_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            media = MediaIoBaseUpload(backup_file, mimetype='application/json')
            
            file_metadata = {
                'name': filename,
                'parents': [self.folder_id] if self.folder_id else []
            }
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            logger.info(f"Backup uploaded successfully: {file.get('id')}")
            return True
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return False
    
    def export_database_data(self):
        """Export all database data for backup"""
        backup_data = {
            'backup_timestamp': datetime.now().isoformat(),
            'current_game': st.session_state.get('current_game'),
            'responses': st.session_state.get('responses', [])
        }
        
        # Try to get data from database if available
        current_game = load_current_game()
        if current_game:
            backup_data['current_game'] = current_game
            df = load_responses(current_game['id'])
            if not df.empty:
                backup_data['responses'] = df.to_dict('records')
        
        return backup_data

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
    
    updates_needed = []
    
    for _, row in df.iterrows():
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
        
        updates_needed.append((row['name'], new_status))
    
    # Apply updates
    for name, status in updates_needed:
        update_response_status(game_id, [name], status)

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
    
    if conf + wait + canc > 0:
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

def show_admin_tab(df: pd.DataFrame, game_id: int, status_filter: str):
    """Show admin management tab for specific status"""
    filtered = df[df['status'] == status_filter][['name', 'others']].reset_index(drop=True)
    
    if not filtered.empty:
        st.table(filtered)
        
        selected = st.multiselect(f"Select from {status_filter}", 
                                 filtered['name'].tolist(), 
                                 key=status_filter)
        
        if selected:
            col1, col2, col3, col4 = st.columns(4)
            
            if col1.button(f"Move ➡️ Confirmed ({status_filter})", key=f"{status_filter}_c"):
                if update_response_status(game_id, selected, '✅ Confirmed'):
                    log_admin_action("admin", f"Moved to Confirmed", f"Players: {', '.join(selected)}")
                    st.toast("Moved to Confirmed.")
                    st.rerun()
            
            if col2.button(f"Move ➡️ Waitlist ({status_filter})", key=f"{status_filter}_w"):
                if update_response_status(game_id, selected, '⏳ Waitlist'):
                    log_admin_action("admin", f"Moved to Waitlist", f"Players: {', '.join(selected)}")
                    st.toast("Moved to Waitlist.")
                    st.rerun()
            
            if col3.button(f"Move ➡️ Cancelled ({status_filter})", key=f"{status_filter}_x"):
                if update_response_status(game_id, selected, '❌ Cancelled'):
                    log_admin_action("admin", f"Moved to Cancelled", f"Players: {', '.join(selected)}")
                    st.toast("Moved to Cancelled.")
                    st.rerun()
            
            if col4.button(f"🗑️ Remove ({status_filter})", key=f"{status_filter}_rm"):
                if delete_responses(game_id, selected):
                    log_admin_action("admin", f"Removed players", f"Players: {', '.join(selected)}")
                    st.toast(f"Removed from {status_filter}.")
                    st.rerun()
    else:
        st.info(f"No players in {status_filter} status")

def show_system_status():
    """Display system status"""
    with st.sidebar.expander("🔧 System Status"):
        conn, db_type = get_connection()
        if conn and db_type == "postgresql":
            st.success("✅ PostgreSQL Connected")
            conn.close()
        elif conn and db_type == "sqlite":
            st.warning("⚠️ SQLite Mode")
            conn.close()
        else:
            st.info("📝 Session Storage Mode")
        
        if GOOGLE_DRIVE_AVAILABLE and "google_drive" in st.secrets:
            st.success("✅ Google Drive Ready")
        else:
            st.warning("⚠️ No Backup Configured")

# --- Initialize System ---
try:
    create_tables()
    logger.info("System initialized successfully")
except Exception as e:
    logger.error(f"Initialization error: {e}")
    st.warning("Using session storage mode")

# --- Main Application ---
st.sidebar.markdown("# 📜 Menu")
section = st.sidebar.selectbox("Navigate to", ["🏀 RSVP", "⚙️ Admin", "📊 Analytics"])

show_system_status()
check_session_timeout()

# --- ADMIN PAGE ---
if section == '⚙️ Admin':
    st.title(":gear: Admin Dashboard")
    
    if not st.session_state.admin_authenticated:
        st.sidebar.markdown("## Admin Login 🔒")
        
        # Debug toggle
        debug_mode = st.sidebar.checkbox("🔍 Debug Mode")
        
        username = st.sidebar.text_input("Username", value="admin")
        password = st.sidebar.text_input("Password", type="password")
        
        if debug_mode:
            st.sidebar.markdown("### Debug Info")
            if "admin_password" in st.secrets:
                expected_pwd = st.secrets["admin_password"]
                st.sidebar.write(f"Available: {list(st.secrets.keys())}")
        
        if st.sidebar.button("Login"):
            if authenticate_admin(username, password):
                st.session_state.admin_authenticated = True
                st.session_state.admin_login_time = datetime.now()
                log_admin_action(username, "Admin login")
                st.success("✅ Login successful!")
                st.rerun()
            else:
                st.sidebar.error("❌ Invalid credentials")
    else:
        # Backup controls
        st.subheader("🔄 Data Management")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📤 Backup to Google Drive"):
                if GOOGLE_DRIVE_AVAILABLE and "google_drive" in st.secrets:
                    backup = GoogleDriveBackup()
                    if backup.backup_database():
                        st.success("Backup completed successfully!")
                        log_admin_action("admin", "Database backup created")
                    else:
                        st.error("Backup failed. Check logs for details.")
                else:
                    st.error("Google Drive not configured. Please check your secrets.")
        
        with col2:
            if GOOGLE_DRIVE_AVAILABLE and "google_drive" in st.secrets:
                st.info("💡 Automatic daily backups recommended")
            else:
                st.warning("⚠️ Google Drive backup not configured")
        
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
                    log_admin_action("admin", "Game scheduled", 
                                   f"Date: {game_date}, Time: {start_time}-{end_time}, Location: {location}")
                    st.rerun()
                else:
                    st.error("Failed to save schedule")

        # Show current game and responses
        current_game = load_current_game()
        if current_game:
            st.markdown(f"**Current Game:** {current_game['game_date']} — "
                       f"**{format_time_str(current_game['start_time'])} to {format_time_str(current_game['end_time'])}** "
                       f"@ **{current_game['location']}**")
            
            df = load_responses(current_game['id'])
            st.subheader(":clipboard: RSVP Overview")
            show_metrics_and_chart(df)
            
            # Download CSV functionality
            if not df.empty:
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Download RSVP CSV", 
                    csv, 
                    f"basketball_rsvp_{current_game['game_date']}.csv", 
                    "text/csv"
                )
            
            with st.expander("📝 Manage Players"):
                tabs = st.tabs(["✅ Confirmed", "⏳ Waitlist", "❌ Cancelled"])
                for i, status in enumerate(['✅ Confirmed', '⏳ Waitlist', '❌ Cancelled']):
                    with tabs[i]:
                        show_admin_tab(df, current_game['id'], status)
            
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
                        st.toast("Teams ready!")
                        st.balloons()
                        log_admin_action("admin", "Teams generated", 
                                       f"Generated {len(teams)} teams with {len(sum(teams, []))} players")
                    else:
                        st.warning("Not enough players.")
            else:
                st.warning("Not enough confirmed players to generate teams.")
        else:
            st.info("No game scheduled yet. Create a game above to start managing RSVPs.")
        
        # Admin logout
        if st.button("🚪 Logout"):
            st.session_state.admin_authenticated = False
            st.session_state.admin_login_time = None
            log_admin_action("admin", "Admin logout")
            st.rerun()

# --- ANALYTICS PAGE ---
elif section == "📊 Analytics":
    st.title(":bar_chart: Analytics Dashboard")
    
    if not st.session_state.admin_authenticated:
        st.warning("Please log in as admin to view analytics.")
        st.info("👈 Use the Admin section in the sidebar to log in.")
    else:
        st.info("📊 Analytics features are being developed!")
        
        # Show some basic stats if we have data
        current_game = load_current_game()
        if current_game:
            df = load_responses(current_game['id'])
            if not df.empty:
                st.subheader("📈 Current Game Statistics")
                show_metrics_and_chart(df)
                
                # Player breakdown by status
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    confirmed = df[df['status'] == '✅ Confirmed']
                    if not confirmed.empty:
                        st.markdown("**✅ Confirmed Players:**")
                        for _, row in confirmed.iterrows():
                            others_count = len([o.strip() for o in str(row.get('others', '')).split(',') if o.strip()])
                            total_count = 1 + others_count
                            if others_count > 0:
                                st.write(f"• {row['name']} (+{others_count} = {total_count} total)")
                            else:
                                st.write(f"• {row['name']}")
                
                with col2:
                    waitlist = df[df['status'] == '⏳ Waitlist']
                    if not waitlist.empty:
                        st.markdown("**⏳ Waitlist:**")
                        for _, row in waitlist.iterrows():
                            st.write(f"• {row['name']}")
                    else:
                        st.info("No players on waitlist")
                
                with col3:
                    cancelled = df[df['status'] == '❌ Cancelled']
                    if not cancelled.empty:
                        st.markdown("**❌ Cancelled:**")
                        for _, row in cancelled.iterrows():
                            st.write(f"• {row['name']}")
                    else:
                        st.info("No cancelled players")
                
                # Response timeline
                if not df.empty:
                    st.subheader("📅 RSVP Timeline")
                    df_timeline = df.copy()
                    df_timeline['timestamp'] = pd.to_datetime(df_timeline['timestamp'])
                    df_timeline = df_timeline.sort_values('timestamp')
                    
                    timeline_chart = alt.Chart(df_timeline).mark_circle(size=100).encode(
                        x=alt.X('timestamp:T', title='Time'),
                        y=alt.Y('name:N', title='Player'),
                        color=alt.Color('status:N', 
                                      scale=alt.Scale(domain=['✅ Confirmed', '⏳ Waitlist', '❌ Cancelled'],
                                                    range=['#4CAF50', '#FFC107', '#F44336'])),
                        tooltip=['name:N', 'status:N', 'timestamp:T', 'others:N']
                    ).properties(
                        width='container',
                        height=300,
                        title="RSVP Timeline"
                    )
                    
                    st.altair_chart(timeline_chart, use_container_width=True)
        else:
            st.info("No game data available for analytics. Schedule a game first!")
        
        st.markdown("### 🔮 Coming Soon:")
        st.markdown("- Player attendance history")
        st.markdown("- Popular time slots analysis")
        st.markdown("- Capacity utilization trends")
        st.markdown("- Player reliability scores")
        st.markdown("- Game frequency statistics")
        st.markdown("- Email notification system")

# --- RSVP PAGE ---
else:
    st.title(":basketball: RSVP & Basketball Game Details")
    
    current_game = load_current_game()
    if not current_game:
        st.warning("📅 No game scheduled yet.")
        st.info("The organizer will schedule the next game soon. Check back later!")
        
        # Show placeholder content
        st.markdown("### 🏀 What to expect:")
        st.markdown("- **Game scheduling** by the organizer")
        st.markdown("- **Easy RSVP** with your name and guests")
        st.markdown("- **Real-time updates** on confirmed players")
        st.markdown("- **Automatic team generation** on game day")
        st.markdown("- **Waitlist management** when games are full")
    else:
        game_date = current_game['game_date']
        if isinstance(game_date, str):
            try:
                game_date = datetime.fromisoformat(game_date).date()
            except:
                game_date = datetime.strptime(game_date, '%Y-%m-%d').date()
        
        deadline = game_date - timedelta(days=CUTOFF_DAYS)
        today = date.today()
        
        # Game details header
        st.markdown(f"### 🏀 Next Game: **{game_date}**")
        
        # Create info columns
        info_col1, info_col2 = st.columns(2)
        with info_col1:
            st.markdown(f"**⏰ Time:** {format_time_str(current_game['start_time'])} to {format_time_str(current_game['end_time'])}")
        with info_col2:
            st.markdown(f"**📍 Location:** {current_game['location']}")
        
        # Game day countdown
        if today < game_date:
            days_until = (game_date - today).days
            if days_until == 0:
                st.success("🎉 Game day is today!")
            elif days_until == 1:
                st.info("🏀 Game is tomorrow!")
            else:
                st.info(f"📅 {days_until} days until the game")
        elif today == game_date:
            st.success("🎉 Game day is today! See you on the court!")
        else:
            st.info("This game has already taken place.")
        
        # Load and display current responses
        df = load_responses(current_game['id'])
        show_metrics_and_chart(df)
        
        # Show player lists
        if not df.empty:
            with st.expander("👥 See who's playing", expanded=True):
                player_col1, player_col2 = st.columns(2)
                
                with player_col1:
                    confirmed = df[df['status'] == '✅ Confirmed']
                    if not confirmed.empty:
                        st.markdown("**✅ Confirmed Players:**")
                        total_confirmed = 0
                        for _, row in confirmed.iterrows():
                            others_str = str(row.get('others', '') or '')
                            others_list = [o.strip() for o in others_str.split(',') if o.strip()]
                            player_count = 1 + len(others_list)
                            total_confirmed += player_count
                            
                            if others_list:
                                st.write(f"• **{row['name']}** + {', '.join(others_list)} ({player_count} total)")
                            else:
                                st.write(f"• **{row['name']}**")
                        
                        st.markdown(f"*Total confirmed players: {total_confirmed}*")
                    else:
                        st.info("No confirmed players yet")
                
                with player_col2:
                    waitlist = df[df['status'] == '⏳ Waitlist']
                    if not waitlist.empty:
                        st.markdown("**⏳ Waitlist:**")
                        for _, row in waitlist.iterrows():
                            others_str = str(row.get('others', '') or '')
                            others_list = [o.strip() for o in others_str.split(',') if o.strip()]
                            if others_list:
                                st.write(f"• {row['name']} + {', '.join(others_list)}")
                            else:
                                st.write(f"• {row['name']}")
                    else:
                        st.info("No players on waitlist")
        
        # RSVP Form
        if today <= deadline:
            st.info(f"🕒 RSVP is open until **{deadline}**")
            
            # Check if user already has an RSVP
            with st.form("rsvp_form"):
                st.markdown("### 📝 Your RSVP")
                name = st.text_input("Your First Name", placeholder="Enter your first name")
                attend = st.select_slider("Will you attend?", ["No ❌", "Yes ✅"], value="Yes ✅")
                others = st.text_input("Additional Players (comma-separated)", 
                                     placeholder="e.g., John, Sarah, Mike")
                
                # Show capacity warning and info
                if attend == "Yes ✅":
                    confirmed_count = len(df[df['status'] == '✅ Confirmed'])
                    others_count = len([o.strip() for o in others.split(',') if o.strip()]) if others else 0
                    total_requesting = 1 + others_count
                    
                    if confirmed_count + total_requesting > CAPACITY:
                        st.warning(f"⚠️ Game is nearly full! You might be placed on the waitlist.")
                    
                    if others_count > 0:
                        st.info(f"ℹ️ You're RSVPing for **{total_requesting} people** total (yourself + {others_count} others)")
                
                submit_button = st.form_submit_button("🎫 Submit RSVP", use_container_width=True)
                
                if submit_button:
                    if not name.strip():
                        st.error("❌ Please enter your name.")
                    else:
                        # Check if name already exists
                        existing = df[df['name'].str.lower() == name.strip().lower()]
                        
                        if add_response(name.strip(), others.strip(), 
                                      attend == "Yes ✅", current_game['id']):
                            update_statuses(current_game['id'])
                            
                            if not existing.empty:
                                st.success("✅ Your RSVP has been updated!")
                                st.info("Your previous RSVP was replaced with this new one.")
                            else:
                                st.success("✅ RSVP recorded successfully!")
                            
                            st.info("🔄 Refreshing page to show updated status...")
                            st.rerun()
                        else:
                            st.error("❌ Failed to record RSVP. Please try again.")
        else:
            st.error(f"⏰ RSVP closed on {deadline}")
            st.info("The RSVP deadline has passed. Contact the organizer if you need to make changes.")
        
        # Show recent activity
        if not df.empty:
            with st.expander("📈 Recent Activity"):
                recent_df = df.sort_values('timestamp', ascending=False).head(5)
                st.markdown("**Latest RSVPs:**")
                for _, row in recent_df.iterrows():
                    timestamp = pd.to_datetime(row['timestamp'])
                    time_ago = datetime.now() - timestamp.replace(tzinfo=None)
                    
                    if time_ago.days > 0:
                        time_str = f"{time_ago.days} day{'s' if time_ago.days > 1 else ''} ago"
                    elif time_ago.seconds > 3600:
                        hours = time_ago.seconds // 3600
                        time_str = f"{hours} hour{'s' if hours > 1 else ''} ago"
                    elif time_ago.seconds > 60:
                        minutes = time_ago.seconds // 60
                        time_str = f"{minutes} minute{'s' if minutes > 1 else ''} ago"
                    else:
                        time_str = "Just now"
                    
                    status_emoji = row['status'] if row['status'] else "🔄"
                    st.write(f"• **{row['name']}** {status_emoji} - {time_str}")

# --- Footer ---
st.sidebar.markdown("---")
st.sidebar.markdown("🏀 **Basketball Organizer**")
#st.sidebar.markdown("Built with Streamlit")

# Show database status
conn, db_type = get_connection()
if conn and db_type == "postgresql":
    st.sidebar.markdown("🗄️ PostgreSQL Database")
    conn.close()
elif conn and db_type == "sqlite":
    st.sidebar.markdown("🗄️ SQLite Database")
    conn.close()
else:
    st.sidebar.markdown("📝 Session Storage")

if GOOGLE_DRIVE_AVAILABLE and "google_drive" in st.secrets:
    st.sidebar.markdown("☁️ Google Drive Backup")

# Show admin hint
if not st.session_state.admin_authenticated:
    st.sidebar.markdown("💡 *Admin features available in Admin section*")

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

# Try to import PostgreSQL driver with fallbacks
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DB_AVAILABLE = True
    logger.info("PostgreSQL driver loaded successfully")
except ImportError as e:
    logger.warning(f"PostgreSQL driver not available: {e}")
    DB_AVAILABLE = False
    # Fallback to SQLite for local development
    try:
        import sqlite3
        SQLITE_AVAILABLE = True
        logger.info("Falling back to SQLite")
    except ImportError:
        SQLITE_AVAILABLE = False
        logger.error("No database drivers available")

# Try to import bcrypt with fallback
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    logger.warning("bcrypt not available, using basic password comparison")
    BCRYPT_AVAILABLE = False

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
    GOOGLE_DRIVE_AVAILABLE = False

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
if "use_fallback_storage" not in st.session_state:
    st.session_state.use_fallback_storage = not DB_AVAILABLE

# --- Database Configuration ---
@st.cache_resource
def init_connection():
    """Initialize database connection with fallbacks"""
    if DB_AVAILABLE:
        try:
            # Try PostgreSQL first
            conn = psycopg2.connect(
                host=st.secrets["database"]["host"],
                database=st.secrets["database"]["dbname"],
                user=st.secrets["database"]["user"],
                password=st.secrets["database"]["password"],
                port=st.secrets["database"]["port"]
            )
            logger.info("PostgreSQL connection established")
            return conn, "postgresql"
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            st.error(f"Database connection failed: {e}")
    
    # Fallback to SQLite for local development
    if SQLITE_AVAILABLE:
        try:
            conn = sqlite3.connect('basketball_app.db', check_same_thread=False)
            logger.info("SQLite connection established")
            return conn, "sqlite"
        except Exception as e:
            logger.error(f"SQLite connection failed: {e}")
    
    return None, None

def create_tables():
    """Create necessary database tables with fallback support"""
    conn_info = init_connection()
    if not conn_info[0]:
        return False
    
    conn, db_type = conn_info
    
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
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id SERIAL PRIMARY KEY,
                    admin_user VARCHAR(100),
                    action VARCHAR(255),
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:  # SQLite
            # SQLite specific SQL
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
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_user TEXT,
                    action TEXT,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def log_admin_action(admin_user: str, action: str, details: str = ""):
    """Log admin actions for audit trail"""
    conn_info = init_connection()
    if not conn_info[0]:
        return
    
    conn, db_type = conn_info
    
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_log (admin_user, action, details)
            VALUES (?, ?, ?)
        """, (admin_user, action, details))
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")
    finally:
        conn.close()

# --- Google Drive Integration ---
class GoogleDriveBackup:
    def __init__(self):
        self.service = None
        if GOOGLE_DRIVE_AVAILABLE:
            self.folder_id = st.secrets.get("google_drive", {}).get("backup_folder_id")
        else:
            self.folder_id = None
    
    def authenticate(self):
        """Authenticate with Google Drive API"""
        if not GOOGLE_DRIVE_AVAILABLE:
            logger.error("Google Drive dependencies not available")
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
        conn_info = init_connection()
        if not conn_info[0]:
            return {}
        
        conn, db_type = conn_info
        
        try:
            if db_type == "postgresql":
                cur = conn.cursor(cursor_factory=RealDictCursor)
            else:
                cur = conn.cursor()
                cur.row_factory = sqlite3.Row
            
            backup_data = {
                'backup_timestamp': datetime.now().isoformat(),
                'games': [],
                'responses': [],
                'audit_log': []
            }
            
            # Export games
            cur.execute("SELECT * FROM games WHERE is_active = 1")
            backup_data['games'] = [dict(row) for row in cur.fetchall()]
            
            # Export responses
            cur.execute("SELECT * FROM responses")
            backup_data['responses'] = [dict(row) for row in cur.fetchall()]
            
            # Export recent audit log (last 30 days)
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
            cur.execute("SELECT * FROM audit_log WHERE timestamp > ? ORDER BY timestamp DESC", (thirty_days_ago,))
            backup_data['audit_log'] = [dict(row) for row in cur.fetchall()]
            
            cur.close()
            return backup_data
            
        except Exception as e:
            logger.error(f"Database export failed: {e}")
            return {}
        finally:
            conn.close()

# --- Authentication Functions ---
def hash_password(password: str) -> str:
    """Hash password using bcrypt or fallback"""
    if BCRYPT_AVAILABLE:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    else:
        # Simple fallback (NOT SECURE - only for development)
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    if BCRYPT_AVAILABLE:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    else:
        # Simple fallback (NOT SECURE - only for development)
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest() == hashed

def create_admin_user(username: str, password: str) -> bool:
    """Create new admin user"""
    conn_info = init_connection()
    if not conn_info[0]:
        return False
    
    conn, db_type = conn_info
    
    try:
        cur = conn.cursor()
        password_hash = hash_password(password)
        
        if db_type == "postgresql":
            cur.execute("""
                INSERT INTO admin_users (username, password_hash)
                VALUES (%s, %s)
                ON CONFLICT (username) DO UPDATE SET password_hash = %s
            """, (username, password_hash, password_hash))
        else:  # SQLite
            cur.execute("""
                INSERT OR REPLACE INTO admin_users (username, password_hash)
                VALUES (?, ?)
            """, (username, password_hash))
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
        return False
    finally:
        conn.close()

def authenticate_admin(username: str, password: str) -> bool:
    """Authenticate admin user"""
    conn_info = init_connection()
    if not conn_info[0]:
        return False
    
    conn, db_type = conn_info
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM admin_users WHERE username = ?", (username,))
        result = cur.fetchone()
        
        if result and verify_password(password, result[0]):
            # Update last login
            cur.execute("UPDATE admin_users SET last_login = ? WHERE username = ?", 
                       (datetime.now().isoformat(), username))
            conn.commit()
            cur.close()
            return True
        
        cur.close()
        return False
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return False
    finally:
        conn.close()

def check_session_timeout():
    """Check if admin session has timed out"""
    if (st.session_state.admin_authenticated and 
        st.session_state.admin_login_time and
        datetime.now() - st.session_state.admin_login_time > timedelta(minutes=SESSION_TIMEOUT_MINUTES)):
        st.session_state.admin_authenticated = False
        st.session_state.admin_login_time = None
        st.warning("Session expired. Please log in again.")
        st.rerun()

# --- Database Functions ---
def save_game(game_date, start_time, end_time, location) -> bool:
    """Save game to database"""
    conn_info = init_connection()
    if not conn_info[0]:
        return False
    
    conn, db_type = conn_info
    
    try:
        cur = conn.cursor()
        # Deactivate previous games
        cur.execute("UPDATE games SET is_active = 0 WHERE is_active = 1")
        
        # Insert new game
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
    """Load current active game"""
    conn_info = init_connection()
    if not conn_info[0]:
        return None
    
    conn, db_type = conn_info
    
    try:
        if db_type == "postgresql":
            cur = conn.cursor(cursor_factory=RealDictCursor)
        else:
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
    """Add or update RSVP response"""
    conn_info = init_connection()
    if not conn_info[0]:
        return False
    
    conn, db_type = conn_info
    
    try:
        cur = conn.cursor()
        status = '❌ Cancelled' if not attend else ''
        
        # Check if response exists
        cur.execute("SELECT id FROM responses WHERE name = ? AND game_id = ?", (name, game_id))
        existing = cur.fetchone()
        
        if existing:
            # Update existing response
            cur.execute("""
                UPDATE responses 
                SET others = ?, status = ?, updated_at = ?
                WHERE id = ?
            """, (others, status, datetime.now().isoformat(), existing[0]))
        else:
            # Insert new response
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
    """Load responses for current game"""
    conn_info = init_connection()
    if not conn_info[0]:
        return pd.DataFrame()
    
    conn, db_type = conn_info
    
    try:
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

def update_response_status(game_id: int, names: List[str], new_status: str) -> bool:
    """Update status for selected responses"""
    conn_info = init_connection()
    if not conn_info[0]:
        return False
    
    conn, db_type = conn_info
    
    try:
        cur = conn.cursor()
        
        if db_type == "postgresql":
            cur.execute("""
                UPDATE responses 
                SET status = %s, updated_at = %s
                WHERE game_id = %s AND name = ANY(%s)
            """, (new_status, datetime.now().isoformat(), game_id, names))
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
        return False
    finally:
        conn.close()

def delete_responses(game_id: int, names: List[str]) -> bool:
    """Delete selected responses"""
    conn_info = init_connection()
    if not conn_info[0]:
        return False
    
    conn, db_type = conn_info
    
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
        return False
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
    df = load_responses(game_id).sort_values('timestamp')
    if df.empty:
        return
    
    conn_info = init_connection()
    if not conn_info[0]:
        return
    
    conn, db_type = conn_info
    
    try:
        cur = conn.cursor()
        cum = 0
        
        for _, row in df.iterrows():
            current_status = row['status']
            if current_status in ['❌ Cancelled', '✅ Confirmed', '⏳ Waitlist']:
                continue  # Keep manual status
            
            others_str = str(row.get('others', '') or '')
            extras = len([o.strip() for o in others_str.split(',') if o.strip()])
            parts = 1 + extras
            
            if cum + parts <= CAPACITY:
                new_status = '✅ Confirmed'
                cum += parts
            else:
                new_status = '⏳ Waitlist'
            
            cur.execute("""
                UPDATE responses 
                SET status = ?, updated_at = ?
                WHERE game_id = ? AND name = ?
            """, (new_status, datetime.now().isoformat(), game_id, row['name']))
        
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"Error updating statuses: {e}")
    finally:
        conn.close()

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
    st.table(filtered)
    
    selected = st.multiselect(f"Select from {status_filter}", 
                             filtered['name'].tolist(), 
                             key=status_filter)
    
    if not selected:
        return
    
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

# --- System Status Display ---
def show_system_status():
    """Display system status and available features"""
    with st.sidebar.expander("🔧 System Status"):
        st.markdown("**Database:**")
        if DB_AVAILABLE:
            st.success("✅ PostgreSQL Available")
        elif SQLITE_AVAILABLE:
            st.warning("⚠️ Using SQLite Fallback")
        else:
            st.error("❌ No Database Available")
        
        st.markdown("**Security:**")
        if BCRYPT_AVAILABLE:
            st.success("✅ Secure Password Hashing")
        else:
            st.warning("⚠️ Basic Password Hashing")
        
        st.markdown("**Backup:**")
        if GOOGLE_DRIVE_AVAILABLE:
            st.success("✅ Google Drive Integration")
        else:
            st.warning("⚠️ Backup Not Available")

# --- Initialize Database ---
if 'db_initialized' not in st.session_state:
    if create_tables():
        st.session_state.db_initialized = True
        # Create default admin user
        admin_password = st.secrets.get("admin_password", "admin123")
        create_admin_user("admin", admin_password)
        logger.info("Database initialized successfully")
    else:
        st.error("Failed to initialize database. Please check your configuration.")
        st.stop()

# --- Main Application ---
st.sidebar.markdown("# 📜 Menu")
section = st.sidebar.selectbox("Navigate to", ["🏀 RSVP", "⚙️ Admin", "📊 Analytics"])

# Show system status
show_system_status()

# Check session timeout
check_session_timeout()

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
                log_admin_action(username, "Admin login")
                st.rerun()
            else:
                st.sidebar.error("Invalid credentials")
    else:
        # Backup controls
        st.subheader("🔄 Data Management")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📤 Backup to Google Drive"):
                if GOOGLE_DRIVE_AVAILABLE:
                    backup = GoogleDriveBackup()
                    if backup.backup_database():
                        st.success("Backup completed successfully!")
                        log_admin_action("admin", "Database backup created")
                    else:
                        st.error("Backup failed. Check logs for details.")
                else:
                    st.error("Google Drive integration not available. Please check your setup.")
        
        with col2:
            if GOOGLE_DRIVE_AVAILABLE:
                st.info("💡 Automatic daily backups are recommended")
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
            
            # Download CSV
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
                
                # Player list by status
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    confirmed = df[df['status'] == '✅ Confirmed']
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
                    st.markdown("**⏳ Waitlist:**")
                    for _, row in waitlist.iterrows():
                        st.write(f"• {row['name']}")
                
                with col3:
                    cancelled = df[df['status'] == '❌ Cancelled']
                    st.markdown("**❌ Cancelled:**")
                    for _, row in cancelled.iterrows():
                        st.write(f"• {row['name']}")
        
        st.markdown("### 🔮 Coming Soon:")
        st.markdown("- Player attendance history")
        st.markdown("- Popular time slots analysis")
        st.markdown("- Capacity utilization trends")
        st.markdown("- Player reliability scores")
        st.markdown("- Game frequency statistics")

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
                # Handle different date formats
                game_date = datetime.strptime(game_date, '%Y-%m-%d').date()
        
        deadline = game_date - timedelta(days=CUTOFF_DAYS)
        today = date.today()
        
        st.markdown(f"### 🏀 Next Game: **{game_date}**")
        st.markdown(f"**Time:** {format_time_str(current_game['start_time'])} to {format_time_str(current_game['end_time'])}")
        st.markdown(f"**Location:** {current_game['location']}")
        
        df = load_responses(current_game['id'])
        show_metrics_and_chart(df)
        
        # Show player lists
        if not df.empty:
            with st.expander("👥 See who's playing"):
                col1, col2 = st.columns(2)
                
                with col1:
                    confirmed = df[df['status'] == '✅ Confirmed']
                    if not confirmed.empty:
                        st.markdown("**✅ Confirmed Players:**")
                        for _, row in confirmed.iterrows():
                            others_str = str(row.get('others', '') or '')
                            others_list = [o.strip() for o in others_str.split(',') if o.strip()]
                            if others_list:
                                st.write(f"• {row['name']} + {', '.join(others_list)}")
                            else:
                                st.write(f"• {row['name']}")
                
                with col2:
                    waitlist = df[df['status'] == '⏳ Waitlist']
                    if not waitlist.empty:
                        st.markdown("**⏳ Waitlist:**")
                        for _, row in waitlist.iterrows():
                            st.write(f"• {row['name']}")
        
        # RSVP Form
        if today <= deadline:
            st.info(f"🕒 RSVP is open until **{deadline}**")
            
            # Check if user already has an RSVP
            with st.form("rsvp_form"):
                st.markdown("### 📝 Your RSVP")
                name = st.text_input("Your First Name", placeholder="Enter your name")
                attend = st.select_slider("Will you attend?", ["No ❌", "Yes ✅"], value="Yes ✅")
                others = st.text_input("Additional Players (comma-separated)", 
                                     placeholder="e.g., John, Sarah, Mike")
                
                # Show capacity warning
                if attend == "Yes ✅":
                    confirmed_count = len(df[df['status'] == '✅ Confirmed'])
                    others_count = len([o.strip() for o in others.split(',') if o.strip()]) if others else 0
                    total_requesting = 1 + others_count
                    
                    if confirmed_count + total_requesting > CAPACITY:
                        st.warning(f"⚠️ Game is nearly full! You might be placed on the waitlist.")
                    
                    if others_count > 0:
                        st.info(f"You're RSVPing for {total_requesting} people total (yourself + {others_count} others)")
                
                submit_button = st.form_submit_button("🎫 Submit RSVP")
                
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
                            else:
                                st.success("✅ RSVP recorded successfully!")
                            
                            st.info("🔄 Refreshing page to show updated status...")
                            st.rerun()
                        else:
                            st.error("❌ Failed to record RSVP. Please try again.")
        else:
            st.error(f"⏰ RSVP closed on {deadline}")
            st.info("The RSVP deadline has passed. Contact the organizer if you need to make changes.")
        
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

# --- Footer ---
st.sidebar.markdown("---")
st.sidebar.markdown("🏀 **Basketball Organizer**")
st.sidebar.markdown("Built with Streamlit")

if DB_AVAILABLE:
    st.sidebar.markdown("🗄️ PostgreSQL Database")
elif SQLITE_AVAILABLE:
    st.sidebar.markdown("🗄️ SQLite Database")

if GOOGLE_DRIVE_AVAILABLE:
    st.sidebar.markdown("☁️ Google Drive Backup")
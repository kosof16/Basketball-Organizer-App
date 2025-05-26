import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, time, timedelta
import random
import altair as alt
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# --- Database Configuration ---
@st.cache_resource
def init_connection():
    """Initialize PostgreSQL connection"""
    try:
        # Use Streamlit secrets for database configuration
        conn = psycopg2.connect(
            host=st.secrets["database"]["host"],
            database=st.secrets["database"]["dbname"],
            user=st.secrets["database"]["user"],
            password=st.secrets["database"]["password"],
            port=st.secrets["database"]["port"]
        )
        return conn
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return None

def create_tables():
    """Create necessary database tables"""
    conn = init_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        
        # Games table
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
        
        # Responses table
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
        
        # Admin users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        """)
        
        # Audit log table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id SERIAL PRIMARY KEY,
                admin_user VARCHAR(100),
                action VARCHAR(255),
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

def log_admin_action(admin_user, action, details=""):
    """Log admin actions for audit trail"""
    conn = init_connection()
    if not conn:
        return
    
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_log (admin_user, action, details)
            VALUES (%s, %s, %s)
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
        self.folder_id = st.secrets.get("google_drive", {}).get("backup_folder_id")
    
    def authenticate(self):
        """Authenticate with Google Drive API"""
        try:
            # Use service account credentials stored in secrets
            credentials_info = st.secrets["google_drive"]["service_account"]
            from google.oauth2 import service_account
            
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
            # Export database data
            backup_data = self.export_database_data()
            
            # Create backup file
            backup_content = json.dumps(backup_data, indent=2, default=str)
            backup_file = io.BytesIO(backup_content.encode())
            
            # Upload to Google Drive
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
        conn = init_connection()
        if not conn:
            return {}
        
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            backup_data = {
                'backup_timestamp': datetime.now().isoformat(),
                'games': [],
                'responses': [],
                'audit_log': []
            }
            
            # Export games
            cur.execute("SELECT * FROM games WHERE is_active = TRUE")
            backup_data['games'] = [dict(row) for row in cur.fetchall()]
            
            # Export responses
            cur.execute("SELECT * FROM responses")
            backup_data['responses'] = [dict(row) for row in cur.fetchall()]
            
            # Export recent audit log (last 30 days)
            cur.execute("""
                SELECT * FROM audit_log 
                WHERE timestamp > %s 
                ORDER BY timestamp DESC
            """, (datetime.now() - timedelta(days=30),))
            backup_data['audit_log'] = [dict(row) for row in cur.fetchall()]
            
            cur.close()
            return backup_data
            
        except Exception as e:
            logger.error(f"Database export failed: {e}")
            return {}
        finally:
            conn.close()

# --- Authentication Functions ---
def hash_password(password):
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, hashed):
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_admin_user(username, password):
    """Create new admin user"""
    conn = init_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        password_hash = hash_password(password)
        cur.execute("""
            INSERT INTO admin_users (username, password_hash)
            VALUES (%s, %s)
            ON CONFLICT (username) DO UPDATE SET password_hash = %s
        """, (username, password_hash, password_hash))
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
        return False
    finally:
        conn.close()

# QUICK FIX: Replace your authenticate_admin function with this one

# Replace your authenticate_admin function with this:

def authenticate_admin(username, password):
    """Simple authentication using secrets directly"""
    try:
        # Get password from secrets with multiple fallback methods
        stored_password = None
        
        # Try different ways to access the secret
        if "admin_password" in st.secrets:
            stored_password = st.secrets["admin_password"]
        elif hasattr(st.secrets, 'admin_password'):
            stored_password = st.secrets.admin_password
        else:
            st.sidebar.error("admin_password not found in secrets!")
            st.sidebar.write(f"Available secrets: {list(st.secrets.keys())}")
            return False
        
        # Clean both strings
        clean_stored = str(stored_password).strip().strip('"').strip("'")
        clean_input_password = str(password).strip()
        clean_input_username = str(username).strip().lower()
        
        # Debug info (remove this after testing)
        if clean_input_username == "admin":
            st.sidebar.write(f"🔍 Expected password: '{clean_stored}'")
            st.sidebar.write(f"🔍 Your input: '{clean_input_password}'")
            st.sidebar.write(f"🔍 Match: {clean_input_password == clean_stored}")
        
        # Simple comparison
        return clean_input_username == "admin" and clean_input_password == clean_stored
        
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

# --- Database Functions ---
def save_game(game_date, start_time, end_time, location):
    """Save game to database"""
    conn = init_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        # Deactivate previous games
        cur.execute("UPDATE games SET is_active = FALSE WHERE is_active = TRUE")
        
        # Insert new game
        cur.execute("""
            INSERT INTO games (game_date, start_time, end_time, location)
            VALUES (%s, %s, %s, %s)
        """, (game_date, start_time, end_time, location))
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error saving game: {e}")
        return False
    finally:
        conn.close()

def load_current_game():
    """Load current active game"""
    conn = init_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM games WHERE is_active = TRUE ORDER BY created_at DESC LIMIT 1")
        result = cur.fetchone()
        cur.close()
        return dict(result) if result else None
    except Exception as e:
        logger.error(f"Error loading game: {e}")
        return None
    finally:
        conn.close()

def add_response(name, others, attend, game_id):
    """Add or update RSVP response"""
    conn = init_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        status = '❌ Cancelled' if not attend else ''
        
        # Check if response exists
        cur.execute("SELECT id FROM responses WHERE name = %s AND game_id = %s", (name, game_id))
        existing = cur.fetchone()
        
        if existing:
            # Update existing response
            cur.execute("""
                UPDATE responses 
                SET others = %s, status = %s, updated_at = %s
                WHERE id = %s
            """, (others, status, datetime.now(), existing[0]))
        else:
            # Insert new response
            cur.execute("""
                INSERT INTO responses (game_id, name, others, status)
                VALUES (%s, %s, %s, %s)
            """, (game_id, name, others, status))
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error adding response: {e}")
        return False
    finally:
        conn.close()

def load_responses(game_id):
    """Load responses for current game"""
    conn = init_connection()
    if not conn:
        return pd.DataFrame()
    
    try:
        query = """
            SELECT name, others, status, timestamp, updated_at
            FROM responses 
            WHERE game_id = %s 
            ORDER BY timestamp ASC
        """
        df = pd.read_sql_query(query, conn, params=(game_id,))
        return df
    except Exception as e:
        logger.error(f"Error loading responses: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def update_response_status(game_id, names, new_status):
    """Update status for selected responses"""
    conn = init_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE responses 
            SET status = %s, updated_at = %s
            WHERE game_id = %s AND name = ANY(%s)
        """, (new_status, datetime.now(), game_id, names))
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error updating response status: {e}")
        return False
    finally:
        conn.close()

def delete_responses(game_id, names):
    """Delete selected responses"""
    conn = init_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM responses 
            WHERE game_id = %s AND name = ANY(%s)
        """, (game_id, names))
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Error deleting responses: {e}")
        return False
    finally:
        conn.close()

# --- Utility Functions ---
def format_time_str(t_str):
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

def update_statuses(game_id):
    """Update response statuses based on capacity"""
    df = load_responses(game_id).sort_values('timestamp')
    if df.empty:
        return
    
    conn = init_connection()
    if not conn:
        return
    
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
                SET status = %s, updated_at = %s
                WHERE game_id = %s AND name = %s
            """, (new_status, datetime.now(), game_id, row['name']))
        
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"Error updating statuses: {e}")
    finally:
        conn.close()

def generate_teams(game_id, num_teams=None):
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

def show_metrics_and_chart(df):
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

def show_admin_tab(df, game_id, status_filter):
    """Show admin management tab for specific status"""
    filtered = df[df['status'] == status_filter][['name', 'others']].reset_index(drop=True)
    st.table(filtered)
    
    selected = st.multiselect(f"Select from {status_filter}", 
                             filtered['name'].tolist(), 
                             key=status_filter)
    
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

# --- Initialize Database ---
if 'db_initialized' not in st.session_state:
    if create_tables():
        st.session_state.db_initialized = True
        # Create default admin user if it doesn't exist
        create_admin_user("admin", st.secrets.get("admin_password", "admin123"))
    else:
        st.error("Failed to initialize database. Please check your configuration.")
        st.stop()

# --- Main Application ---
st.sidebar.markdown("# 📜 Menu")
section = st.sidebar.selectbox("Navigate to", ["🏀 RSVP", "⚙️ Admin", "📊 Analytics"])

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
                backup = GoogleDriveBackup()
                if backup.backup_database():
                    st.success("Backup completed successfully!")
                    log_admin_action("admin", "Database backup created")
                else:
                    st.error("Backup failed. Check logs for details.")
        
        with col2:
            st.info("💡 Automatic daily backups are recommended")
        
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
                        for i, team in enumerate(teams, 1):
                            st.markdown(f"**Team {i}:** {', '.join(team)}")
                        st.toast("Teams ready!")
                        st.balloons()
                        log_admin_action("admin", "Teams generated", 
                                       f"Generated {len(teams)} teams")
                    else:
                        st.warning("Not enough players.")
            else:
                st.warning("Not enough confirmed players to generate teams.")

# --- ANALYTICS PAGE ---
elif section == "📊 Analytics":
    st.title(":bar_chart: Analytics Dashboard")
    
    if not st.session_state.admin_authenticated:
        st.warning("Please log in as admin to view analytics.")
    else:
        # TODO: Add analytics features
        st.info("Analytics features coming soon!")
        st.markdown("### Planned Features:")
        st.markdown("- Player attendance statistics")
        st.markdown("- Popular time slots analysis")
        st.markdown("- Capacity utilization trends")
        st.markdown("- Player reliability scores")

# --- RSVP PAGE ---
else:
    st.title(":basketball: RSVP & Basketball Game Details")
    
    current_game = load_current_game()
    if not current_game:
        st.warning("No game scheduled.")
    else:
        game_date = current_game['game_date']
        if isinstance(game_date, str):
            game_date = datetime.fromisoformat(game_date).date()
        
        deadline = game_date - timedelta(days=CUTOFF_DAYS)
        today = date.today()
        
        st.markdown(f"### Next Game: **{game_date}** from "
                   f"**{format_time_str(current_game['start_time'])}** to "
                   f"**{format_time_str(current_game['end_time'])}** @ "
                   f"**{current_game['location']}**")
        
        df = load_responses(current_game['id'])
        show_metrics_and_chart(df)
        
        if today < deadline:
            st.info(f"RSVP open until **{deadline}** 🕒")
            
            with st.form("rsvp_form"):
                name = st.text_input("Your First Name")
                attend = st.select_slider("Will you attend?", ["No ❌", "Yes ✅"], value="Yes ✅")
                others = st.text_input("Additional Players (comma-separated)")
                
                if st.form_submit_button("Submit RSVP 🎫"):
                    if not name.strip():
                        st.error("Name is required.")
                    else:
                        if add_response(name.strip(), others.strip(), 
                                      attend == "Yes ✅", current_game['id']):
                            update_statuses(current_game['id'])
                            st.success("RSVP recorded!")
                            st.rerun()
                        else:
                            st.error("Failed to record RSVP. Please try again.")
        else:
            st.error(f"RSVP closed on {deadline}. See you next time!")

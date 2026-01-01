"""
Basketball Organizer App - Refactored Version
Main application file using modular architecture
"""

import streamlit as st
import pandas as pd
import logging
from datetime import datetime, date, timedelta
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import configuration and constants
from src.config import Config, AppConfig
from src.constants import EVENT_TYPES, CUSTOM_CSS, NAV_OPTIONS

# Import services
from src.services.auth_service import authenticate_admin, check_session_timeout, log_admin_action, logout_admin
from src.services.game_service import save_game, load_current_game
from src.services.rsvp_service import add_response, load_responses, update_statuses, update_response_status, delete_responses
from src.services.calendar_service import (create_calendar_event, update_calendar_event,
                                           delete_calendar_event, get_events_for_date, get_events_for_month)
from src.services.team_service import generate_teams

# Import utilities
from src.utils.helpers import format_time_str
from src.utils.session import init_session_state

# Import database
from src.models.database import create_tables

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Page Config (Must be first) ---
st.set_page_config(
    page_title=AppConfig.PAGE_TITLE,
    layout=AppConfig.LAYOUT,
    initial_sidebar_state=AppConfig.INITIAL_SIDEBAR_STATE,
    menu_items=AppConfig.MENU_ITEMS
)

# Apply custom CSS
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# === INITIALIZATION ===
init_session_state()

# Initialize database tables if needed
if not st.session_state.tables_initialized:
    db_config = Config.get_database_config()
    from src.models.database import get_connection
    conn, db_type = get_connection(db_config)
    if create_tables(conn, db_type):
        st.session_state.tables_initialized = True
        logger.info("Database tables initialized successfully")
    else:
        logger.warning("Failed to initialize database tables, using session state storage")

# === HELPER FUNCTIONS FOR UI ===

def show_system_status():
    """Display system status in sidebar"""
    from src.models.database import DB_AVAILABLE, SQLITE_AVAILABLE

    with st.sidebar.expander("ℹ️ System Status", expanded=False):
        db_status = "✅ PostgreSQL" if DB_AVAILABLE and Config.get_database_config() else \
                   "⚠️ SQLite" if SQLITE_AVAILABLE else "📝 Session State"
        st.caption(f"**Database:** {db_status}")
        st.caption(f"**Version:** {AppConfig.VERSION}")


def show_metrics_and_chart(df: pd.DataFrame):
    """Display metrics and charts for game status"""
    import altair as alt

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

    # Display metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("✅ Confirmed", confirmed,
                 f"{total_confirmed_players} total players")

    with col2:
        st.metric("⏳ Waitlist", waitlist)

    with col3:
        st.metric("❌ Cancelled", cancelled)

    with col4:
        capacity_percentage = (total_confirmed_players / Config.CAPACITY) * 100
        st.metric("📊 Capacity", f"{capacity_percentage:.0f}%",
                 f"{total_confirmed_players}/{Config.CAPACITY}")

    # Capacity chart
    if not df.empty:
        chart_data = pd.DataFrame({
            'Status': ['Confirmed', 'Available', 'Waitlist'],
            'Count': [
                total_confirmed_players,
                max(0, Config.CAPACITY - total_confirmed_players),
                waitlist
            ],
            'Color': ['#4CAF50', '#E0E0E0', '#FF9800']
        })

        chart = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X('Count:Q', title='Players'),
            y=alt.Y('Status:N', title=''),
            color=alt.Color('Color:N', scale=None, legend=None),
            tooltip=['Status', 'Count']
        ).properties(height=150)

        st.altair_chart(chart, use_container_width=True)


# === MAIN APPLICATION ===

# Main Navigation
st.sidebar.title(AppConfig.PAGE_TITLE)
st.sidebar.markdown("---")

selected_page = st.sidebar.radio(
    "Navigate to:",
    options=list(NAV_OPTIONS.keys()),
    index=0,
    key="navigation"
)

current_section = NAV_OPTIONS[selected_page]

# Show system status
show_system_status()

# Check session timeout for admin pages
if current_section in ["admin", "analytics"]:
    check_session_timeout()

# === RSVP PAGE ===
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
    else:
        # Parse game date
        game_date = current_game['game_date']
        if isinstance(game_date, str):
            game_date = datetime.fromisoformat(game_date).date()

        deadline = game_date - timedelta(days=Config.CUTOFF_DAYS)
        today = date.today()

        # Game header
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

        # RSVP Form
        st.markdown("### 📝 RSVP for this Game")

        with st.form("rsvp_form"):
            name = st.text_input("Your Name *", placeholder="Enter your full name")
            others = st.text_input("Bringing others? (optional)",
                                   placeholder="e.g., John, Sarah",
                                   help="Enter names separated by commas")
            attend = st.radio("Will you attend?", ["Yes", "No"], horizontal=True)

            submitted = st.form_submit_button("Submit RSVP", use_container_width=True)

            if submitted:
                if not name.strip():
                    st.error("Please enter your name")
                else:
                    is_attending = attend == "Yes"
                    if add_response(name.strip(), others.strip(), is_attending, current_game['id']):
                        update_statuses(current_game['id'])
                        if is_attending:
                            st.success(f"✅ Thanks {name}! You're registered for the game.")
                        else:
                            st.info(f"Cancelled your registration. Hope to see you next time!")
                        st.rerun()
                    else:
                        st.error("Failed to submit RSVP. Please try again.")

# === CALENDAR PAGE ===
elif current_section == "calendar":
    st.title("📅 Basketball Calendar")

    # Calendar implementation would go here
    # (Keeping this section for the full implementation)
    st.info("Calendar view - showing all upcoming events")

# === ADMIN PAGE ===
elif current_section == "admin":
    st.title("⚙️ Admin Panel")

    if not st.session_state.admin_authenticated:
        st.markdown("### 🔐 Admin Login")

        with st.form("admin_login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            login_button = st.form_submit_button("Login")

            if login_button:
                if authenticate_admin(username, password):
                    st.success("✅ Login successful!")
                    st.rerun()
                else:
                    st.error("❌ Invalid credentials")
    else:
        st.success(f"✅ Logged in as admin")

        if st.button("🚪 Logout"):
            logout_admin()
            st.rerun()

        st.markdown("---")

        # Admin features
        tab1, tab2 = st.tabs(["📅 Schedule Game", "👥 Manage RSVPs"])

        with tab1:
            st.markdown("### Schedule New Game")

            with st.form("schedule_game"):
                game_date_input = st.date_input("Game Date", value=date.today() + timedelta(days=7))
                col1, col2 = st.columns(2)
                with col1:
                    start_time_input = st.time_input("Start Time", value=datetime.strptime("19:00", "%H:%M").time())
                with col2:
                    end_time_input = st.time_input("End Time", value=datetime.strptime("21:00", "%H:%M").time())

                location_input = st.text_input("Location", value=Config.DEFAULT_LOCATION)

                schedule_button = st.form_submit_button("📅 Schedule Game", use_container_width=True)

                if schedule_button:
                    if save_game(game_date_input, start_time_input, end_time_input, location_input):
                        log_admin_action("admin", "Game Scheduled",
                                       f"Date: {game_date_input}, Location: {location_input}")
                        st.success("✅ Game scheduled successfully!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to schedule game")

# === ANALYTICS PAGE ===
elif current_section == "analytics":
    st.title("📊 Analytics")

    if not st.session_state.admin_authenticated:
        st.warning("🔐 Please login as admin to view analytics")
    else:
        st.info("Analytics dashboard - player statistics, attendance trends, etc.")

# === SIDEBAR INFO ===
st.sidebar.markdown("---")
st.sidebar.caption(f"Basketball Organizer v{AppConfig.VERSION}")
st.sidebar.caption("Refactored Architecture ✨")

"""
Basketball Organizer App - Enhanced Version with Gamification
Main application file with gamification, notifications, and waitlist features
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
from src.constants import EVENT_TYPES, CUSTOM_CSS

# Import services
from src.services.auth_service import authenticate_admin, check_session_timeout, log_admin_action, logout_admin
from src.services.game_service import save_game, load_current_game
from src.services.rsvp_service import add_response, load_responses, update_statuses, update_response_status, delete_responses
from src.services.calendar_service import (create_calendar_event, update_calendar_event,
                                           delete_calendar_event, get_events_for_date, get_events_for_month)
from src.services.team_service import generate_teams
from src.services.gamification_service import (
    init_gamification_storage, get_player_stats, update_player_stats,
    check_achievements, get_leaderboard, get_player_points
)
from src.services.waitlist_service import (
    get_waitlist_stats, promote_from_waitlist, get_waitlist_position,
    handle_cancellation_promotion
)
from src.services.notification_service import email_service

# Import utilities
from src.utils.helpers import format_time_str
from src.utils.session import init_session_state

# Import database
from src.models.database import create_tables

# Import UI components
from src.components.gamification_ui import (
    display_player_profile, display_leaderboard,
    display_achievement_notification, display_points_badge
)

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
init_gamification_storage()

# Initialize database tables if needed
if not st.session_state.tables_initialized:
    db_config = Config.get_database_config()
    from src.models.database import get_connection
    conn, db_type = get_connection(db_config)
    if create_tables(conn, db_type):
        st.session_state.tables_initialized = True
        logger.info("Database tables initialized successfully")

# Check for new achievements
if "last_player_name" in st.session_state and st.session_state.last_player_name:
    new_achievements = check_achievements(st.session_state.last_player_name)
    if new_achievements and "shown_achievements" not in st.session_state:
        st.session_state.shown_achievements = []

    for achievement_id in new_achievements:
        if achievement_id not in st.session_state.shown_achievements:
            display_achievement_notification(achievement_id)
            st.session_state.shown_achievements.append(achievement_id)

# === HELPER FUNCTIONS ===

def show_system_status():
    """Display system status in sidebar"""
    from src.models.database import DB_AVAILABLE, SQLITE_AVAILABLE

    with st.sidebar.expander("ℹ️ System Status", expanded=False):
        db_status = "✅ PostgreSQL" if DB_AVAILABLE and Config.get_database_config() else \
                   "⚠️ SQLite" if SQLITE_AVAILABLE else "📝 Session State"
        st.caption(f"**Database:** {db_status}")

        email_status = "✅ Enabled" if email_service.enabled else "⚠️ Not configured"
        st.caption(f"**Email:** {email_status}")

        st.caption(f"**Version:** {AppConfig.VERSION} (Enhanced)")


def show_metrics_and_chart(df: pd.DataFrame, game_id: int):
    """Display metrics and charts with waitlist info"""
    import altair as alt

    # Get waitlist stats
    waitlist_stats = get_waitlist_stats(game_id)

    # Display metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("✅ Confirmed", waitlist_stats["confirmed_count"],
                 f"{waitlist_stats['utilization_percent']:.0f}% capacity")

    with col2:
        st.metric("⏳ Waitlist", waitlist_stats["waitlist_count"],
                 help="Players waiting for spots")

    with col3:
        st.metric("📊 Capacity", f"{Config.CAPACITY}",
                 f"{waitlist_stats['available_spots']} spots left")

    with col4:
        cancelled = len(df[df['status'] == '❌ Cancelled'])
        st.metric("❌ Cancelled", cancelled)

    # Capacity visualization
    chart_data = pd.DataFrame({
        'Status': ['Confirmed', 'Available', 'Waitlist'],
        'Count': [
            waitlist_stats["confirmed_count"],
            waitlist_stats["available_spots"],
            waitlist_stats["waitlist_count"]
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


# === NAVIGATION ===

NAV_OPTIONS = {
    "🏀 RSVP": "rsvp",
    "📊 My Stats": "stats",
    "🏆 Leaderboard": "leaderboard",
    "📅 Calendar": "calendar",
    "⚙️ Admin": "admin"
}

st.sidebar.title(AppConfig.PAGE_TITLE)
st.sidebar.markdown("---")

selected_page = st.sidebar.radio(
    "Navigate to:",
    options=list(NAV_OPTIONS.keys()),
    index=0,
    key="navigation"
)

current_section = NAV_OPTIONS[selected_page]

# Show player's points in sidebar
if "last_player_name" in st.session_state and st.session_state.last_player_name:
    player_points = get_player_points(st.session_state.last_player_name)
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Your Points")
    display_points_badge(player_points)

# Show system status
show_system_status()

# Check session timeout for admin pages
if current_section == "admin":
    check_session_timeout()

# === RSVP PAGE ===
if current_section == "rsvp":
    st.title("🏀 Basketball Game RSVP")

    current_game = load_current_game()

    if not current_game:
        st.warning("📅 No game scheduled yet")
        st.info("The organizer will schedule the next game soon. Check back later!")

        # Show leaderboard preview
        st.markdown("---")
        st.markdown("### 🏆 Top Players")
        leaderboard = get_leaderboard("points", limit=5)
        if leaderboard:
            for rank, (name, points) in enumerate(leaderboard, 1):
                medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank}."
                st.markdown(f"{medal} **{name}** - {points:,} points")
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
        show_metrics_and_chart(df, current_game['id'])

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

                    # Check if early RSVP (>24h before game)
                    hours_until_game = (datetime.combine(game_date, datetime.min.time()) - datetime.now()).total_seconds() / 3600
                    is_early = hours_until_game > 24

                    # Count guests
                    guests_list = [g.strip() for g in others.split(',') if g.strip()]
                    guests_count = len(guests_list)

                    if add_response(name.strip(), others.strip(), is_attending, current_game['id']):
                        # Update statuses (handles waitlist logic)
                        update_statuses(current_game['id'])

                        # Update gamification stats
                        if is_attending:
                            update_player_stats(
                                name.strip(),
                                "rsvp_confirmed",
                                {
                                    "is_early": is_early,
                                    "guests_count": guests_count,
                                    "game_date": game_date
                                }
                            )

                            # Check status after update
                            df_updated = load_responses(current_game['id'])
                            player_row = df_updated[df_updated['name'] == name.strip()]

                            if not player_row.empty:
                                status = player_row.iloc[0]['status']

                                if status == '✅ Confirmed':
                                    points_earned = 10 + (5 if is_early else 0) + (guests_count * 5)
                                    st.success(f"✅ You're in! Earned {points_earned} points!")

                                    # Send confirmation email
                                    # email_service.send_rsvp_confirmation(...)

                                elif status == '⏳ Waitlist':
                                    position = get_waitlist_position(current_game['id'], name.strip())
                                    st.warning(f"⏳ Game is full. You're #{position} on the waitlist.")
                                    st.info("We'll notify you if a spot opens up!")

                            st.session_state.last_player_name = name.strip()
                        else:
                            # Handle cancellation
                            update_player_stats(name.strip(), "cancelled", {"game_date": game_date})

                            # Promote from waitlist
                            promoted = handle_cancellation_promotion(current_game['id'])
                            if promoted:
                                st.info(f"Cancelled. {len(promoted)} player(s) promoted from waitlist!")
                            else:
                                st.info("Cancelled your registration. Hope to see you next time!")

                        st.rerun()
                    else:
                        st.error("Failed to submit RSVP. Please try again.")

        # Player lists with waitlist
        with st.expander("👥 **Player List**", expanded=True):
            tab1, tab2, tab3 = st.tabs(["✅ Confirmed", "⏳ Waitlist", "❌ Cancelled"])

            with tab1:
                confirmed = df[df['status'] == '✅ Confirmed']
                if not confirmed.empty:
                    for _, row in confirmed.iterrows():
                        others_str = str(row.get('others', '') or '')
                        guests = [g for g in others_str.split(',') if g.strip()]
                        guest_text = f" (+{len(guests)})" if guests else ""
                        st.markdown(f"• **{row['name']}**{guest_text}")
                else:
                    st.info("No confirmed players yet. Be the first!")

            with tab2:
                waitlist = df[df['status'] == '⏳ Waitlist']
                if not waitlist.empty:
                    st.info(f"📊 {len(waitlist)} player(s) on waitlist")
                    for idx, row in waitlist.iterrows():
                        position = get_waitlist_position(current_game['id'], row['name'])
                        st.markdown(f"{position}. **{row['name']}**")
                else:
                    st.info("No waitlist yet")

            with tab3:
                cancelled = df[df['status'] == '❌ Cancelled']
                if not cancelled.empty:
                    for _, row in cancelled.iterrows():
                        st.markdown(f"• {row['name']}")
                else:
                    st.info("No cancellations")

# === MY STATS PAGE ===
elif current_section == "stats":
    st.title("📊 My Stats & Achievements")

    # Get player name
    player_name = st.session_state.get("last_player_name")

    if not player_name:
        st.info("👋 Enter your name to view your stats!")
        player_name = st.text_input("Your Name:", key="stats_player_name")

        if player_name:
            st.session_state.last_player_name = player_name
            st.rerun()
    else:
        # Display full profile
        display_player_profile(player_name)

        # Option to change player
        if st.button("View Another Player"):
            del st.session_state.last_player_name
            st.rerun()

# === LEADERBOARD PAGE ===
elif current_section == "leaderboard":
    st.title("🏆 Leaderboard")

    display_leaderboard()

    # Show current player's rank
    if "last_player_name" in st.session_state and st.session_state.last_player_name:
        st.markdown("---")
        st.markdown("### 📍 Your Position")

        player_name = st.session_state.last_player_name
        from src.services.gamification_service import get_player_rank

        col1, col2, col3 = st.columns(3)
        with col1:
            rank = get_player_rank(player_name, "points")
            st.metric("Points Rank", f"#{rank}" if rank > 0 else "N/A")
        with col2:
            rank = get_player_rank(player_name, "games_attended")
            st.metric("Games Rank", f"#{rank}" if rank > 0 else "N/A")
        with col3:
            rank = get_player_rank(player_name, "attendance_rate")
            st.metric("Attendance Rank", f"#{rank}" if rank > 0 else "N/A")

# === ADMIN PAGE ===
elif current_section == "admin":
    st.title("⚙️ Admin Panel")

    if not st.session_state.admin_authenticated:
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
        st.success("✅ Logged in as admin")

        if st.button("🚪 Logout"):
            logout_admin()
            st.rerun()

        st.markdown("---")

        tab1, tab2, tab3 = st.tabs(["📅 Schedule Game", "👥 Manage RSVPs", "🎮 Gamification"])

        with tab1:
            with st.form("schedule_game"):
                game_date_input = st.date_input("Game Date", value=date.today() + timedelta(days=7))
                col1, col2 = st.columns(2)
                with col1:
                    start_time_input = st.time_input("Start Time", value=datetime.strptime("19:00", "%H:%M").time())
                with col2:
                    end_time_input = st.time_input("End Time", value=datetime.strptime("21:00", "%H:%M").time())

                location_input = st.text_input("Location", value=Config.DEFAULT_LOCATION)

                if st.form_submit_button("📅 Schedule Game", use_container_width=True):
                    if save_game(game_date_input, start_time_input, end_time_input, location_input):
                        log_admin_action("admin", "Game Scheduled", f"Date: {game_date_input}")
                        st.success("✅ Game scheduled!")
                        st.rerun()

        with tab3:
            st.markdown("### 🎮 Gamification Overview")

            leaderboard = get_leaderboard("points", limit=10)
            total_players = len(leaderboard)
            total_points = sum(pts for _, pts in leaderboard)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Players", total_players)
            with col2:
                st.metric("Total Points", f"{total_points:,}")
            with col3:
                avg_points = total_points / total_players if total_players > 0 else 0
                st.metric("Avg Points", f"{avg_points:.0f}")

# === SIDEBAR INFO ===
st.sidebar.markdown("---")
st.sidebar.caption(f"Basketball Organizer v{AppConfig.VERSION}")
st.sidebar.caption("✨ Enhanced with Gamification")

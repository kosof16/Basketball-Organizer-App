"""Constants for Basketball Organizer App"""

# Event types for calendar
EVENT_TYPES = {
    "🏀 Game": {"color": "#4CAF50", "icon": "🏀"},
    "🏃 Training": {"color": "#2196F3", "icon": "🏃"},
    "🏆 Tournament": {"color": "#FF9800", "icon": "🏆"},
    "🎉 Social": {"color": "#9C27B0", "icon": "🎉"},
    "📋 Meeting": {"color": "#607D8B", "icon": "📋"},
    "🚫 Cancelled": {"color": "#F44336", "icon": "🚫"}
}

# RSVP Status Options
STATUS_CONFIRMED = "✅ Confirmed"
STATUS_CANCELLED = "❌ Cancelled"
STATUS_MAYBE = "🤔 Maybe"
STATUS_PENDING = ""

# Navigation Options
NAV_OPTIONS = {
    "🏀 RSVP": "rsvp",
    "📅 Calendar": "calendar",
    "⚙️ Admin": "admin",
    "📊 Analytics": "analytics"
}

# Custom CSS for UI
CUSTOM_CSS = """
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
"""

# Session State Defaults
SESSION_DEFAULTS = {
    "admin_authenticated": False,
    "admin_login_time": None,
    "current_game": None,
    "responses": [],
    "calendar_events": [],
    "selected_date": None,  # Will be set to date.today() dynamically
    "show_edit_form": False,
    "editing_event_id": None,
    "last_refresh": None,  # Will be set to datetime.now() dynamically
    "connection_cache": None,
    "user_preferences": {
        "theme": "light",
        "notifications": True,
        "auto_refresh": True
    },
    "tables_initialized": False
}

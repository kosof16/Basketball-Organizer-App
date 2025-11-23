"""Configuration management for Basketball Organizer App"""
import os
import streamlit as st
from typing import Optional, Dict, Any


class Config:
    """Application configuration"""

    # Game Settings
    CAPACITY: int = int(os.getenv('GAME_CAPACITY', '15'))
    DEFAULT_LOCATION: str = "Arc: Health and Fitness Centre"
    CUTOFF_DAYS: int = int(os.getenv('RSVP_CUTOFF_DAYS', '1'))

    # Session Settings
    SESSION_TIMEOUT_MINUTES: int = 30
    CACHE_TTL: int = 300  # 5 minutes cache

    # Database Settings
    @staticmethod
    def get_database_config() -> Optional[Dict[str, Any]]:
        """Get database configuration from secrets"""
        if "database" in st.secrets:
            return {
                "host": st.secrets["database"]["host"],
                "database": st.secrets["database"]["dbname"],
                "user": st.secrets["database"]["user"],
                "password": st.secrets["database"]["password"],
                "port": st.secrets["database"]["port"],
                "connect_timeout": 10
            }
        return None

    # Google Drive Settings
    @staticmethod
    def get_google_drive_config() -> Optional[Dict[str, Any]]:
        """Get Google Drive configuration from secrets"""
        if "google_drive" in st.secrets:
            return st.secrets["google_drive"]
        return None

    # Admin Settings
    @staticmethod
    def get_admin_credentials() -> Optional[Dict[str, str]]:
        """Get admin credentials from secrets"""
        if "admin" in st.secrets:
            return {
                "username": st.secrets["admin"].get("username"),
                "password_hash": st.secrets["admin"].get("password_hash")
            }
        return None


class AppConfig:
    """Application-wide configuration"""

    PAGE_TITLE = "🏀 Basketball Organizer"
    LAYOUT = "wide"
    INITIAL_SIDEBAR_STATE = "expanded"

    MENU_ITEMS = {
        'Get Help': 'https://github.com/yourusername/basketball-organizer',
        'Report a bug': "https://github.com/yourusername/basketball-organizer/issues",
        'About': "# Basketball Organizer\nOrganize your basketball games with ease!"
    }

    VERSION = "2.1"

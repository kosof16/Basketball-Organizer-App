"""Session state management utilities"""
import streamlit as st
from datetime import datetime, date
from src.constants import SESSION_DEFAULTS


def init_session_state() -> None:
    """Initialize all session state variables with defaults"""
    for key, value in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            # Handle dynamic defaults
            if key == "selected_date":
                st.session_state[key] = date.today()
            elif key == "last_refresh":
                st.session_state[key] = datetime.now()
            else:
                st.session_state[key] = value

"""Authentication service for admin users"""
import hashlib
import logging
import streamlit as st
from datetime import datetime, timedelta
from typing import Optional
from src.config import Config

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """
    Hash password for comparison

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    return hashlib.sha256(password.encode()).hexdigest()


def authenticate_admin(username: str, password: str) -> bool:
    """
    Authenticate admin user

    Args:
        username: Admin username
        password: Admin password

    Returns:
        True if authentication successful, False otherwise
    """
    try:
        # Get admin credentials
        admin_password = st.secrets.get("admin_password", "")
        admin_username = st.secrets.get("admin_username", "admin")

        # Clean inputs
        clean_username = username.strip().lower()
        clean_password = password.strip()

        # For demo purposes, we'll use simple comparison
        # In production, use proper password hashing (bcrypt)
        is_authenticated = (clean_username == admin_username.lower() and
                           clean_password == admin_password)

        if is_authenticated:
            st.session_state.admin_authenticated = True
            st.session_state.admin_login_time = datetime.now()
            log_admin_action("admin", "Login", "Successful authentication")

        return is_authenticated

    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return False


def check_session_timeout() -> None:
    """Check if admin session has timed out and logout if necessary"""
    if (st.session_state.admin_authenticated and
        st.session_state.admin_login_time and
        datetime.now() - st.session_state.admin_login_time > timedelta(minutes=Config.SESSION_TIMEOUT_MINUTES)):
        st.session_state.admin_authenticated = False
        st.session_state.admin_login_time = None
        st.warning("⏱️ Session expired. Please log in again.")
        st.rerun()


def logout_admin() -> None:
    """Logout current admin user"""
    if st.session_state.admin_authenticated:
        log_admin_action("admin", "Logout", "User logged out")
        st.session_state.admin_authenticated = False
        st.session_state.admin_login_time = None


def log_admin_action(admin_user: str, action: str, details: str = "") -> None:
    """
    Log admin actions with timestamp for audit trail

    Args:
        admin_user: Username of admin performing action
        action: Action being performed
        details: Additional details about the action
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] Admin: {admin_user} | Action: {action} | Details: {details}"
    logger.info(log_entry)

    # Store in session state for audit trail
    if "admin_logs" not in st.session_state:
        st.session_state.admin_logs = []
    st.session_state.admin_logs.append(log_entry)

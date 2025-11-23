"""Calendar event management service"""
import logging
import streamlit as st
from datetime import datetime, date
from datetime import time as time_type
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def create_calendar_event(title: str, event_date: date, start_time: time_type, end_time: time_type,
                          event_type: str, location: str, description: str = "") -> bool:
    """
    Create a new calendar event

    Args:
        title: Event title
        event_date: Date of the event
        start_time: Start time
        end_time: End time
        event_type: Type of event (Game, Training, etc.)
        location: Event location
        description: Optional description

    Returns:
        True if successful, False otherwise
    """
    try:
        event_id = len(st.session_state.calendar_events) + 1
        event = {
            'id': event_id,
            'title': title,
            'date': event_date.isoformat(),
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'type': event_type,
            'location': location,
            'description': description,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        st.session_state.calendar_events.append(event)
        return True
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}")
        return False


def update_calendar_event(event_id: int, **kwargs) -> bool:
    """
    Update an existing calendar event

    Args:
        event_id: ID of the event to update
        **kwargs: Fields to update

    Returns:
        True if successful, False otherwise
    """
    try:
        for event in st.session_state.calendar_events:
            if event['id'] == event_id:
                for key, value in kwargs.items():
                    if key in ['date', 'start_time', 'end_time']:
                        event[key] = value.isoformat() if hasattr(value, 'isoformat') else str(value)
                    else:
                        event[key] = value
                event['updated_at'] = datetime.now().isoformat()
                return True
        return False
    except Exception as e:
        logger.error(f"Error updating calendar event: {e}")
        return False


def delete_calendar_event(event_id: int) -> bool:
    """
    Delete a calendar event

    Args:
        event_id: ID of the event to delete

    Returns:
        True if successful, False otherwise
    """
    try:
        st.session_state.calendar_events = [
            e for e in st.session_state.calendar_events if e['id'] != event_id
        ]
        return True
    except Exception as e:
        logger.error(f"Error deleting calendar event: {e}")
        return False


def get_events_for_date(target_date: date) -> List[Dict[str, Any]]:
    """
    Get all events for a specific date

    Args:
        target_date: Date to get events for

    Returns:
        List of events sorted by start time
    """
    events = []
    for event in st.session_state.calendar_events:
        event_date = datetime.fromisoformat(event['date']).date()
        if event_date == target_date:
            events.append(event)
    return sorted(events, key=lambda x: x['start_time'])


def get_events_for_month(year: int, month: int) -> Dict[int, List[Dict[str, Any]]]:
    """
    Get all events for a specific month

    Args:
        year: Year
        month: Month (1-12)

    Returns:
        Dictionary mapping day numbers to lists of events
    """
    events_by_day = {}
    for event in st.session_state.calendar_events:
        event_date = datetime.fromisoformat(event['date']).date()
        if event_date.year == year and event_date.month == month:
            day = event_date.day
            if day not in events_by_day:
                events_by_day[day] = []
            events_by_day[day].append(event)
    return events_by_day

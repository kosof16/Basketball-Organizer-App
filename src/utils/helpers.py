"""Utility helper functions for Basketball Organizer App"""
from datetime import datetime
from typing import Union
from datetime import time as time_type


def format_time_str(t_str: Union[str, time_type]) -> str:
    """
    Format time string for display

    Args:
        t_str: Time as string or time object

    Returns:
        Formatted time string in 12-hour format
    """
    try:
        if isinstance(t_str, str):
            if 'T' in t_str:  # ISO format
                t = datetime.fromisoformat(t_str).time()
            else:
                # Try different time formats
                for fmt in ['%H:%M:%S', '%H:%M', '%I:%M %p', '%I:%M:%S %p']:
                    try:
                        t = datetime.strptime(t_str, fmt).time()
                        break
                    except:
                        continue
                else:
                    # If all fail, return original string
                    return str(t_str)
        else:
            t = t_str
    except:
        return str(t_str)

    # Format time in a cross-platform way
    hour = t.hour
    minute = t.minute

    # Convert to 12-hour format
    if hour == 0:
        hour_12 = 12
        period = "AM"
    elif hour < 12:
        hour_12 = hour
        period = "AM"
    elif hour == 12:
        hour_12 = 12
        period = "PM"
    else:
        hour_12 = hour - 12
        period = "PM"

    # Format the time string
    if minute == 0:
        return f"{hour_12}:00 {period}"
    else:
        return f"{hour_12}:{minute:02d} {period}"

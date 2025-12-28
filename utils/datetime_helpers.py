"""
Datetime utility functions for consistent timezone handling across the bot
"""
import datetime


def utc_now():
    """Get current UTC datetime with timezone info"""
    return datetime.datetime.now(datetime.timezone.utc)


def ensure_utc(dt):
    """Ensure datetime has UTC timezone info"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def get_timestamp(dt):
    """Get Unix timestamp from datetime, handling timezone properly"""
    if dt is None:
        return None
    dt = ensure_utc(dt)
    return int(dt.timestamp())


def format_discord_timestamp(dt, format_type="F"):
    """Format datetime for Discord timestamp display"""
    if dt is None:
        return "Unknown"
    timestamp = get_timestamp(dt)
    return f"<t:{timestamp}:{format_type}>"
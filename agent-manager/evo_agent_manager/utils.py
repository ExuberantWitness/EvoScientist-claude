"""Utility functions for the agent manager."""

import datetime
import uuid


def generate_session_id() -> str:
    """Generate a short unique session ID."""
    return uuid.uuid4().hex[:8]


def now_iso() -> str:
    """Current time in ISO format."""
    return datetime.datetime.now().isoformat(timespec="seconds")


def truncate(text: str, max_len: int = 2000) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n... [truncated]"

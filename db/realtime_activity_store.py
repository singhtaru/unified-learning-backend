"""
In-memory per-user activity counts by weekday (Mon–Sun).

Keys per user are English day abbreviations ``Mon`` … ``Sun`` (same labels as
``datetime.now().strftime("%%a")`` in typical English locales). Not persisted
across process restarts.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)

activity_store: Dict[str, Dict[str, int]] = {}
_lock = threading.Lock()

DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _current_day_key() -> str:
    """Calendar weekday as Mon–Sun (``weekday()``: 0 = Monday)."""
    return DAY_ORDER[datetime.now().weekday()]


def record_action(email: str, action: str | None = None) -> None:
    """
    Increment today's bucket for ``email`` (normalized store key).
    ``action`` is recorded at debug level; counts are aggregated per weekday only.
    """
    key = _normalize_email(email)
    if not key or key in ("null", "undefined"):
        return
    day = _current_day_key()
    if action:
        logger.debug("activity +1 email=%r action=%r day=%s", key, action, day)
    with _lock:
        if key not in activity_store:
            activity_store[key] = {}
        if day not in activity_store[key]:
            activity_store[key][day] = 0
        activity_store[key][day] += 1


def get_week_activity(email: str) -> List[int]:
    """
    Activity counts Mon→Sun for the graph (``[Mon, Tue, …, Sun]``).

    Store keys are normalized lowercase emails; ``email`` may be any casing.
    """
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    key = _normalize_email(email)
    if not key or key in ("null", "undefined"):
        return [0, 0, 0, 0, 0, 0, 0]
    with _lock:
        if key not in activity_store:
            return [0, 0, 0, 0, 0, 0, 0]
        user_data = activity_store[key]
        return [int(user_data.get(day, 0)) for day in days]


def get_activity_series(email: str) -> List[int]:
    """Same as :func:`get_week_activity` (alias for callers)."""
    return get_week_activity(email)

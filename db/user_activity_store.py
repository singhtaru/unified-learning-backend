import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional

from config.settings import settings


def _db_path() -> str:
    return os.getenv("USERS_DB_PATH", settings.users_db_path)


@contextmanager
def _get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def init_user_activity_storage() -> None:
    with _get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                date TEXT NOT NULL,
                time_spent_minutes INTEGER NOT NULL DEFAULT 0,
                courses_interested INTEGER NOT NULL DEFAULT 0,
                last_session_at TEXT,
                UNIQUE(user_email, date)
            )
            """
        )


def touch_login_session(user_email: str) -> None:
    """Create or update today's row and refresh session timestamp (login)."""
    init_user_activity_storage()
    key = _normalize_email(user_email)
    day = _utc_today().isoformat()
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO user_activity (user_email, date, time_spent_minutes, courses_interested, last_session_at)
            VALUES (?, ?, 0, 0, ?)
            ON CONFLICT(user_email, date) DO UPDATE SET
                last_session_at = excluded.last_session_at
            """,
            (key, day, now),
        )


def increment_courses_interested(user_email: str, delta: int = 1) -> None:
    """Bump today's interested count (new 'Interested' save)."""
    if delta <= 0:
        return
    init_user_activity_storage()
    key = _normalize_email(user_email)
    day = _utc_today().isoformat()
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO user_activity (user_email, date, time_spent_minutes, courses_interested, last_session_at)
            VALUES (?, ?, 0, ?, ?)
            ON CONFLICT(user_email, date) DO UPDATE SET
                courses_interested = user_activity.courses_interested + excluded.courses_interested,
                last_session_at = excluded.last_session_at
            """,
            (key, day, delta, now),
        )


def add_time_minutes_today(user_email: str, minutes: int) -> None:
    """Add study/engagement minutes to today's aggregate."""
    if minutes <= 0:
        return
    init_user_activity_storage()
    key = _normalize_email(user_email)
    day = _utc_today().isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO user_activity (user_email, date, time_spent_minutes, courses_interested, last_session_at)
            VALUES (?, ?, ?, 0, NULL)
            ON CONFLICT(user_email, date) DO UPDATE SET
                time_spent_minutes = user_activity.time_spent_minutes + excluded.time_spent_minutes
            """,
            (key, day, minutes),
        )


def _row_active_for_streak(row: Optional[sqlite3.Row]) -> bool:
    if row is None:
        return False
    t = int(row["time_spent_minutes"] or 0)
    c = int(row["courses_interested"] or 0)
    return t > 0 or c > 0


def _load_activity_map(user_email: str) -> Dict[str, sqlite3.Row]:
    init_user_activity_storage()
    key = _normalize_email(user_email)
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT date, time_spent_minutes, courses_interested FROM user_activity WHERE user_email = ?",
            (key,),
        ).fetchall()
    return {str(r["date"]): r for r in rows}


def compute_streak(activity_by_date: Dict[str, sqlite3.Row], today: date) -> int:
    """
    Consecutive days with learning activity (minutes or interested), counting backward.
    If today is empty but yesterday had activity, start from yesterday (same-calendar grace).
    """
    d = today
    if not _row_active_for_streak(activity_by_date.get(d.isoformat())):
        d = today - timedelta(days=1)
        if not _row_active_for_streak(activity_by_date.get(d.isoformat())):
            return 0

    streak = 0
    while _row_active_for_streak(activity_by_date.get(d.isoformat())):
        streak += 1
        d -= timedelta(days=1)
    return streak


def build_progress_payload(
    user_email: str,
    *,
    saved_courses_count: int,
    daily_goal_minutes: int,
    chart_days: int,
) -> Dict[str, Any]:
    activity_by_date = _load_activity_map(user_email)
    today = _utc_today()

    total_minutes = sum(int(r["time_spent_minutes"] or 0) for r in activity_by_date.values())
    total_hours = round(total_minutes / 60.0, 2)

    streak = compute_streak(activity_by_date, today)

    today_key = today.isoformat()
    today_row = activity_by_date.get(today_key)
    today_minutes = int(today_row["time_spent_minutes"] or 0) if today_row else 0
    goal = max(1, int(daily_goal_minutes))
    daily_goal_progress = round(min(1.0, today_minutes / float(goal)), 4)

    n_days = max(1, min(int(chart_days), 90))
    activity_chart: List[Dict[str, Any]] = []
    for i in range(n_days - 1, -1, -1):
        d = today - timedelta(days=i)
        key = d.isoformat()
        r = activity_by_date.get(key)
        activity_chart.append(
            {
                "date": key,
                "time_spent_minutes": int(r["time_spent_minutes"] or 0) if r else 0,
                "courses_interested": int(r["courses_interested"] or 0) if r else 0,
            }
        )

    return {
        "total_hours": total_hours,
        "streak": streak,
        "active_courses": int(saved_courses_count),
        "daily_goal_progress": daily_goal_progress,
        "activity": activity_chart,
    }

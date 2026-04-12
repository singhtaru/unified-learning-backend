import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Generator, List, Optional, Tuple

from config.settings import settings

logger = logging.getLogger(__name__)


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


def _migrate_user_courses_table(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(user_courses)").fetchall()
    col_names = {r[1] for r in rows}
    if "duration" not in col_names:
        conn.execute(
            "ALTER TABLE user_courses ADD COLUMN duration TEXT NOT NULL DEFAULT ''"
        )


def init_user_courses_storage() -> None:
    with _get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                course_title TEXT NOT NULL,
                platform TEXT NOT NULL,
                link TEXT NOT NULL,
                duration TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(user_email, link)
            )
            """
        )
        _migrate_user_courses_table(conn)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def save_user_course(
    *,
    user_email: str,
    course_title: str,
    platform: str,
    link: str,
    duration: str = "",
) -> Tuple[dict, bool]:
    """
    Insert a saved course for the user. Returns (row_dict, created_new).
    If the same user_email + link exists, returns the existing row and created_new=False.
    """
    init_user_courses_storage()
    key = _normalize_email(user_email)
    title = course_title.strip()
    plat = platform.strip()
    url = link.strip()
    dur = (duration or "").strip()
    now = datetime.now(timezone.utc).isoformat()

    with _get_conn() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO user_courses (user_email, course_title, platform, link, duration, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (key, title, plat, url, dur, now),
            )
            row_id = int(cur.lastrowid)
        except sqlite3.IntegrityError:
            row = conn.execute(
                """
                SELECT id, user_email, course_title, platform, link, duration, created_at
                FROM user_courses
                WHERE user_email = ? AND link = ?
                """,
                (key, url),
            ).fetchone()
            if row is None:
                logger.warning("IntegrityError on user_courses but row not found for %r", key)
                raise
            return _row_to_dict(row), False

        row = conn.execute(
            """
            SELECT id, user_email, course_title, platform, link, duration, created_at
            FROM user_courses WHERE id = ?
            """,
            (row_id,),
        ).fetchone()
        assert row is not None
        return _row_to_dict(row), True


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": int(row["id"]),
        "user_email": row["user_email"],
        "course_title": row["course_title"],
        "platform": row["platform"],
        "link": row["link"],
        "duration": row["duration"],
        "created_at": row["created_at"],
    }


def course_public(row: dict) -> dict:
    """Response shape after saving a course (includes link for deep-linking)."""
    return {
        "id": row["id"],
        "user_email": row["user_email"],
        "course_title": row["course_title"],
        "platform": row["platform"],
        "link": row["link"],
        "duration": row.get("duration") or "",
        "created_at": row["created_at"],
    }


def history_item(row: dict) -> dict:
    """History list entry for the logged-in user (no PII beyond what they own)."""
    return {
        "id": row["id"],
        "title": row["course_title"],
        "platform": row["platform"],
        "duration": row.get("duration") or "",
        "created_at": row["created_at"],
    }


def _parse_created_at_date(created_at: str) -> Optional[date]:
    if not created_at or not str(created_at).strip():
        return None
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).date()
    except (TypeError, ValueError):
        return None


def activity_counts_last_days(rows: List[dict], days: int = 7) -> List[int]:
    """Number of saves per UTC calendar day, oldest day first (length ``days``)."""
    n = max(1, min(int(days), 90))
    today = datetime.now(timezone.utc).date()
    out: List[int] = []
    for offset in range(n - 1, -1, -1):
        d = today - timedelta(days=offset)
        cnt = sum(
            1
            for r in rows
            if _parse_created_at_date(r.get("created_at") or "") == d
        )
        out.append(cnt)
    return out


def streak_days_from_saved_courses(rows: List[dict]) -> int:
    """Consecutive UTC days with at least one save, with same-day grace as other streak logic."""
    dates = {
        d
        for r in rows
        if (d := _parse_created_at_date(r.get("created_at") or "")) is not None
    }
    if not dates:
        return 0

    today = datetime.now(timezone.utc).date()

    def active(d: date) -> bool:
        return d in dates

    d = today
    if not active(d):
        d = today - timedelta(days=1)
        if not active(d):
            return 0

    streak = 0
    while active(d):
        streak += 1
        d -= timedelta(days=1)
    return streak


def list_saved_courses_for_user(user_email: str) -> List[dict]:
    init_user_courses_storage()
    key = _normalize_email(user_email)
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, user_email, course_title, platform, link, duration, created_at
            FROM user_courses
            WHERE user_email = ?
            ORDER BY datetime(created_at) DESC, id DESC
            """,
            (key,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_saved_courses(user_email: str) -> int:
    init_user_courses_storage()
    key = _normalize_email(user_email)
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM user_courses WHERE user_email = ?",
            (key,),
        ).fetchone()
    return int(row[0]) if row else 0

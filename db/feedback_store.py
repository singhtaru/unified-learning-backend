import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple


DB_PATH = os.getenv("FEEDBACK_DB_PATH", "feedback.db")


@contextmanager
def _get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _maybe_migrate_legacy_feedback(conn: sqlite3.Connection) -> None:
    """One-time copy from legacy ``feedback`` table when ``course_feedback`` is still empty."""
    n = int(conn.execute("SELECT COUNT(*) FROM course_feedback").fetchone()[0])
    if n > 0:
        return
    legacy = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'"
    ).fetchone()
    if not legacy:
        return
    conn.execute(
        """
        INSERT INTO course_feedback (user_email, course_id, rating, comment, created_at)
        SELECT user_id, course_id, rating, '', timestamp
        FROM feedback AS f
        WHERE f.id IN (
            SELECT MAX(id) FROM feedback GROUP BY user_id, course_id
        )
        """
    )


def init_feedback_storage() -> None:
    with _get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS course_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                course_id TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                comment TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(user_email, course_id)
            )
            """
        )
        _maybe_migrate_legacy_feedback(conn)


def save_feedback(
    user_email: str,
    course_id: str,
    rating: int,
    comment: str,
    timestamp: Optional[datetime] = None,
) -> Tuple[int, bool]:
    """
    Insert or update feedback for (user_email, course_id). Returns (feedback_id, created_new).
    """
    init_feedback_storage()
    key = _normalize_email(user_email)
    cid = course_id.strip()
    ts = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    body = (comment or "").strip()

    with _get_conn() as conn:
        existed = conn.execute(
            "SELECT 1 FROM course_feedback WHERE user_email = ? AND course_id = ?",
            (key, cid),
        ).fetchone()

        conn.execute(
            """
            INSERT INTO course_feedback (user_email, course_id, rating, comment, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_email, course_id) DO UPDATE SET
                rating = excluded.rating,
                comment = excluded.comment,
                created_at = excluded.created_at
            """,
            (key, cid, rating, body, ts),
        )
        row = conn.execute(
            "SELECT id FROM course_feedback WHERE user_email = ? AND course_id = ?",
            (key, cid),
        ).fetchone()
        if row is None:
            raise RuntimeError("feedback upsert failed to resolve row id")
        fid = int(row[0])
        created_new = existed is None
        return fid, created_new


def get_average_ratings(course_ids: List[str]) -> Dict[str, float]:
    """Return average rating per course_id for the provided list."""
    if not course_ids:
        return {}

    init_feedback_storage()
    placeholders = ",".join("?" for _ in course_ids)
    query = f"""
        SELECT course_id, AVG(rating) AS avg_rating
        FROM course_feedback
        WHERE course_id IN ({placeholders})
        GROUP BY course_id
    """
    with _get_conn() as conn:
        rows = conn.execute(query, course_ids).fetchall()

    return {str(course_id): float(avg_rating) for course_id, avg_rating in rows}


def get_average_rating(course_id: str) -> float:
    """Average rating (1–5) for a single course; 0.0 if there is no feedback yet."""
    m = get_average_ratings([course_id])
    return float(m.get(course_id.strip(), 0.0))


def get_feedback_count_for_course(course_id: str) -> int:
    """Number of distinct users who left feedback for this course."""
    init_feedback_storage()
    cid = course_id.strip()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM course_feedback WHERE course_id = ?",
            (cid,),
        ).fetchone()
    return int(row[0]) if row else 0


def get_recent_feedback(limit: int = 10) -> List[Dict[str, Any]]:
    """Most recent feedback rows (by id descending)."""
    init_feedback_storage()
    lim = max(1, min(int(limit), 500))
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, user_email, course_id, rating, comment, created_at
            FROM course_feedback
            ORDER BY id DESC
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "user_email": r[1],
            "course_id": r[2],
            "rating": r[3],
            "comment": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]

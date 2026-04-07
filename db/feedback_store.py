import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List


DB_PATH = os.getenv("FEEDBACK_DB_PATH", "feedback.db")


@contextmanager
def _get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_feedback_storage() -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                course_id TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                timestamp TEXT NOT NULL
            )
            """
        )


def save_feedback(user_id: str, course_id: str, rating: int, timestamp: datetime) -> int:
    init_feedback_storage()
    with _get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO feedback (user_id, course_id, rating, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, course_id, rating, timestamp.astimezone(timezone.utc).isoformat()),
        )
        return int(cursor.lastrowid)


def get_average_ratings(course_ids: List[str]) -> Dict[str, float]:
    """Return average rating per course_id for the provided list."""
    if not course_ids:
        return {}

    init_feedback_storage()
    placeholders = ",".join("?" for _ in course_ids)
    query = f"""
        SELECT course_id, AVG(rating) AS avg_rating
        FROM feedback
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
    """Number of feedback rows recorded for this course."""
    init_feedback_storage()
    cid = course_id.strip()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE course_id = ?",
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
            SELECT id, user_id, course_id, rating, timestamp
            FROM feedback
            ORDER BY id DESC
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "user_id": r[1],
            "course_id": r[2],
            "rating": r[3],
            "timestamp": r[4],
        }
        for r in rows
    ]

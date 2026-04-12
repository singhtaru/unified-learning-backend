import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Generator, List, Optional

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


def _migrate_users_table(conn: sqlite3.Connection) -> None:
    """Align legacy DBs with the current schema (add columns, normalize empty defaults)."""
    rows = conn.execute("PRAGMA table_info(users)").fetchall()
    col_names = {r[1] for r in rows}

    if "profile_pic" not in col_names:
        conn.execute("ALTER TABLE users ADD COLUMN profile_pic TEXT")

    conn.execute("UPDATE users SET bio = '' WHERE bio IS NULL")
    conn.execute(
        "UPDATE users SET skills = '[]' WHERE skills IS NULL OR TRIM(COALESCE(skills, '')) = ''"
    )


def init_users_storage() -> None:
    with _get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                bio TEXT NOT NULL DEFAULT '',
                skills TEXT NOT NULL DEFAULT '[]',
                profile_pic TEXT
            )
            """
        )
        _migrate_users_table(conn)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _parse_skills(raw: Optional[str]) -> List[Any]:
    if raw is None or str(raw).strip() == "":
        return []
    try:
        data = json.loads(raw)
        return list(data) if isinstance(data, list) else []
    except json.JSONDecodeError:
        logger.warning("Invalid skills JSON in DB; returning empty list")
        return []


def get_user_by_email(email: str) -> Optional[dict]:
    init_users_storage()
    key = _normalize_email(email)
    with _get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, name, email, password_hash, bio, skills, profile_pic
            FROM users WHERE email = ?
            """,
            (key,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "email": row["email"],
        "password_hash": row["password_hash"],
        "bio": row["bio"] if row["bio"] is not None else "",
        "skills": _parse_skills(row["skills"]),
        "profile_pic": row["profile_pic"],
    }


def get_user_by_id(user_id: int) -> Optional[dict]:
    init_users_storage()
    with _get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, name, email, password_hash, bio, skills, profile_pic
            FROM users WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "email": row["email"],
        "password_hash": row["password_hash"],
        "bio": row["bio"] if row["bio"] is not None else "",
        "skills": _parse_skills(row["skills"]),
        "profile_pic": row["profile_pic"],
    }


def create_user(name: str, email: str, password_hash: str) -> int:
    init_users_storage()
    key = _normalize_email(email)
    with _get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (name, email, password_hash, bio, skills, profile_pic)
            VALUES (?, ?, ?, '', '[]', NULL)
            """,
            (name.strip(), key, password_hash),
        )
        return int(cur.lastrowid)


def apply_profile_updates(user_id: int, updates: dict) -> Optional[dict]:
    """Apply only keys present in ``updates`` (from ``model_dump(exclude_unset=True)``)."""
    init_users_storage()
    if get_user_by_id(user_id) is None:
        return None

    parts: List[str] = []
    vals: List[Any] = []
    if "bio" in updates:
        parts.append("bio = ?")
        vals.append("" if updates["bio"] is None else updates["bio"])
    if "skills" in updates:
        parts.append("skills = ?")
        skills = updates["skills"]
        vals.append("[]" if skills is None else json.dumps(skills))
    if "profile_pic" in updates:
        parts.append("profile_pic = ?")
        vals.append(updates["profile_pic"])
    if not parts:
        return get_user_by_id(user_id)

    vals.append(user_id)
    with _get_conn() as conn:
        conn.execute(f"UPDATE users SET {', '.join(parts)} WHERE id = ?", vals)

    return get_user_by_id(user_id)


def public_profile(row: dict) -> dict:
    raw_skills = row.get("skills")
    if isinstance(raw_skills, list):
        skills_out: List[Any] = raw_skills
    else:
        skills_out = _parse_skills(raw_skills if isinstance(raw_skills, str) else None)

    bio = row.get("bio")
    return {
        "name": row["name"],
        "email": row["email"],
        "bio": "" if bio is None else bio,
        "skills": skills_out,
        "profile_pic": row.get("profile_pic"),
    }

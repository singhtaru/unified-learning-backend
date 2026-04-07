"""
Normalize records from :mod:`services.web_courses` into the same course shape as ``data/courses.json``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from services.course_ids import build_course_id
from services.web_courses import fetch_courses_from_web


def _first_str(raw: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = raw.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _normalize_course_id_value(value: Any) -> str:
    s = str(value).strip()
    if not s:
        return ""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", s).strip("-").lower()
    return slug[:240] if slug else ""


def _unique_course_id(raw: Dict[str, Any], title: str, index: int) -> str:
    for key in ("course_id", "id", "uuid", "slug", "code"):
        v = raw.get(key)
        if v is not None:
            if isinstance(v, dict) and "$oid" in v:
                cid = _normalize_course_id_value(v["$oid"])
                if cid:
                    return cid
            else:
                cid = _normalize_course_id_value(v)
                if cid:
                    return cid
    oid = raw.get("_id")
    if isinstance(oid, dict) and "$oid" in oid:
        cid = _normalize_course_id_value(oid["$oid"])
        if cid:
            return cid
    if oid is not None:
        cid = _normalize_course_id_value(oid)
        if cid:
            return cid
    return build_course_id("web", f"{title}-{index}")


def map_fetched_row_to_course_schema(raw: Dict[str, Any], index: int) -> Optional[Dict[str, str]]:
    """
    Map an arbitrary fetched dict into the backend course schema.

    Fixed fields: ``platform=web``, ``duration=varies``, ``level=unknown``, ``goal=learning``.
    ``course_id`` and ``title`` are derived from the row when possible.
    """
    title = _first_str(
        raw,
        "title",
        "name",
        "courseTitle",
        "course_title",
        "label",
        "courseName",
    )
    if not title:
        return None

    course_id = _unique_course_id(raw, title, index)
    if not course_id:
        course_id = build_course_id("web", f"{title}-{index}")

    return {
        "course_id": course_id,
        "title": title,
        "platform": "web",
        "duration": "varies",
        "level": "unknown",
        "goal": "learning",
    }


def map_fetched_courses_to_schema(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Map a list of raw dicts; drops rows with no mappable title."""
    out: List[Dict[str, str]] = []
    for i, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        mapped = map_fetched_row_to_course_schema(raw, i)
        if mapped is not None:
            out.append(mapped)
    return out


def fetch_courses_from_web_normalized(
    url: str | None = None,
    *,
    timeout: float = 30.0,
) -> List[Dict[str, str]]:
    """
    Fetch JSON from a public URL and return courses in backend schema
    (``course_id``, ``title``, ``platform``, ``duration``, ``level``, ``goal``).

    Uses :func:`services.web_courses.fetch_courses_from_web` then
    :func:`map_fetched_courses_to_schema`.
    """
    raw_rows = fetch_courses_from_web(url=url, timeout=timeout)
    return map_fetched_courses_to_schema(raw_rows)


# Backwards-friendly alias matching the earlier ``fetch_courses_from_web`` naming pattern.
def fetch_external_courses_normalized(
    url: str | None = None,
    *,
    timeout: float = 30.0,
) -> List[Dict[str, str]]:
    """Alias for :func:`fetch_courses_from_web_normalized`."""
    return fetch_courses_from_web_normalized(url=url, timeout=timeout)

"""
HTTP retrieval of course suggestions from a configured search API.

Maps JSON objects to :class:`~models.response_models.CourseRecommendation`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal

import httpx

from config.settings import settings
from models.response_models import CourseRecommendation
from services.course_ids import build_course_id

logger = logging.getLogger(__name__)


def _first_str(d: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _map_api_item_to_course(
    raw: Any,
    *,
    source: Literal["new"] = "new",
) -> Optional[CourseRecommendation]:
    if not isinstance(raw, dict):
        return None
    title = _first_str(raw, "title", "name", "course_title", "courseTitle")
    platform = _first_str(raw, "platform", "provider", "vendor", "site")
    duration = _first_str(raw, "duration", "length", "time", "weeks")
    reason = _first_str(raw, "reason", "summary", "description", "blurb", "overview")
    course_id = _first_str(raw, "course_id", "id", "courseId", "uuid", "slug")

    if not title or not platform:
        return None
    if not duration:
        duration = "flexible"
    if not reason:
        reason = f"Listed on {platform} as a match for your search and preferences."
    if not course_id:
        course_id = build_course_id(platform, title)
    return CourseRecommendation(
        course_id=course_id,
        title=title,
        platform=platform,
        duration=duration,
        reason=reason,
        source=source,
    )


def _extract_course_list(payload: Any) -> List[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("courses", "results", "data", "items", "recommendations"):
            val = payload.get(key)
            if isinstance(val, list):
                return val
    return []


def fetch_courses_for_preferences(
    query: str,
    level: str,
    duration: str,
    goal: str,
    *,
    limit: int = 5,
    source: Literal["new"] = "new",
) -> List[CourseRecommendation]:
    """
    GET the configured course-search API with learner preferences and map results
    to ``CourseRecommendation`` (``course_id``, ``title``, ``platform``, ``duration``, ``reason``).

    Returns an empty list if ``COURSE_SEARCH_API_URL`` is unset or the request / parsing fails.
    """
    base = (settings.course_search_api_url or "").strip()
    if not base:
        logger.warning(
            "course_search_api_url is not set (COURSE_SEARCH_API_KEY optional); no API courses returned",
        )
        return []

    params: Dict[str, Any] = {
        "query": (query or "").strip(),
        "level": (level or "").strip(),
        "duration": (duration or "").strip(),
        "goal": (goal or "").strip(),
        "limit": max(1, min(limit, 50)),
    }
    headers: Dict[str, str] = {"Accept": "application/json"}
    key = (settings.course_search_api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    timeout = float(settings.course_search_timeout_seconds)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(base, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.exception("Course search API request failed: %s", exc)
        return []

    rows = _extract_course_list(payload)
    out: List[CourseRecommendation] = []
    for raw in rows:
        if len(out) >= limit:
            break
        course = _map_api_item_to_course(raw, source=source)
        if course is not None:
            out.append(course)
    if not out:
        logger.warning("Course search API returned no mappable courses (query=%r)", query[:120])
    return out

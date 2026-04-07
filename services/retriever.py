import json
import logging
from typing import Any, Dict, List, Literal, Optional

from models.response_models import CourseRecommendation
from services.course_ids import build_course_id
from services.data_loader import load_courses
from services.external_data_service import map_fetched_courses_to_schema
from services.web_courses import fetch_courses_from_web

logger = logging.getLogger(__name__)


def _semantic_search_query(
    query: Optional[str],
    level: Optional[str] = None,
    duration: Optional[str] = None,
    goal: Optional[str] = None,
) -> str:
    """
    Build the text used for Weaviate embedding search: join only non-empty fields in order.

    Example: ``query='machine learning'``, ``level='beginner'``, ``goal='job'`` →
    ``'machine learning beginner job'``. Missing, None, or whitespace-only values are skipped.
    """
    parts: List[str] = []
    for raw in (query, level, duration, goal):
        if raw is None:
            continue
        s = str(raw).strip()
        if s:
            parts.append(s)
    combined = " ".join(parts)
    return " ".join(combined.split()).lower()


def merge_dedupe_weaviate_first(
    weaviate_courses: List[CourseRecommendation],
    additional_courses: List[CourseRecommendation],
) -> List[CourseRecommendation]:
    """Combine lists with Weaviate rows first; skip duplicate course_ids."""
    seen: set[str] = set()
    out: List[CourseRecommendation] = []
    for c in weaviate_courses + additional_courses:
        if c.course_id in seen:
            continue
        seen.add(c.course_id)
        out.append(c)
    return out


def parse_stored_courses_from_response(
    response_str: str,
    source: Literal["memory", "hybrid", "new"] = "memory",
) -> List[CourseRecommendation]:
    """
    Parse JSON stored in Weaviate ``response`` into courses.

    The ``source`` argument is authoritative: a ``source`` field inside the JSON, if
    present, is ignored so labels match the agent path (memory vs hybrid).
    """
    try:
        parsed = json.loads(response_str)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Invalid JSON in Weaviate response (source=%s): %s",
            source,
            exc,
        )
        return []
    if not isinstance(parsed, list):
        logger.warning(
            "Weaviate response JSON is not a list (source=%s); skipping",
            source,
        )
        return []
    out: List[CourseRecommendation] = []
    for rec in parsed:
        try:
            if not isinstance(rec, dict):
                continue
            title = str(rec.get("title", "")).strip()
            platform = str(rec.get("platform", "")).strip()
            course_duration = str(rec.get("duration", "")).strip()
            reason = str(rec.get("reason", "")).strip()
            if not (title and platform and course_duration and reason):
                continue
            course_id = str(rec.get("course_id", "")).strip() or build_course_id(platform, title)
            try:
                fs = float(rec.get("feedback_score", 0) or 0)
            except (TypeError, ValueError):
                fs = 0.0
            # Do not use rec.get("source") — caller supplies the correct label for this path.
            out.append(
                CourseRecommendation(
                    course_id=course_id,
                    title=title,
                    platform=platform,
                    duration=course_duration,
                    reason=reason,
                    explanation="",
                    feedback_score=max(0.0, fs),
                    source=source,
                )
            )
        except Exception as exc:
            logger.warning(
                "Skipping malformed course entry in Weaviate response (source=%s): %s",
                source,
                exc,
            )
    return out


def _map_weaviate_to_courses(
    weaviate_results: List[Dict[str, object]],
    source: Literal["hybrid"] = "hybrid",
    max_courses: Optional[int] = 5,
) -> List[CourseRecommendation]:
    """For each Weaviate hit, parse ``response`` JSON into ``CourseRecommendation`` objects."""
    mapped: List[CourseRecommendation] = []
    for item in weaviate_results:
        try:
            response_raw = item.get("response")
            if not isinstance(response_raw, str):
                continue
            mapped.extend(parse_stored_courses_from_response(response_raw, source=source))
            if max_courses is not None and len(mapped) >= max_courses:
                return mapped[:max_courses]
        except Exception as exc:
            logger.warning(
                "Failed to map Weaviate hit to courses (source=%s): %s",
                source,
                exc,
            )
    return mapped


def _query_matches_title(query: str, title: str) -> bool:
    """
    Split ``query`` into keywords (whitespace-separated); match if **any** keyword appears
    in ``title``. Comparisons use ``.lower()`` on both sides.

    Example: ``'machine learning'`` matches ``'Machine Learning by Andrew Ng'`` because
    ``'machine'`` or ``'learning'`` appears in the lowercased title.
    """
    t = (title or "").strip().lower()
    raw = (query or "").strip().lower()
    if not raw:
        return False
    keywords = [w for w in raw.split() if len(w) >= 2]
    if not keywords:
        return raw in t
    return any(kw in t for kw in keywords)


def _catalog_row_to_recommendation(
    row: Dict[str, Any],
    *,
    source: Literal["new", "dataset", "web"] = "new",
) -> Optional[CourseRecommendation]:
    """Map a ``courses.json`` row to ``CourseRecommendation``."""
    try:
        title = str(row.get("title", "")).strip()
        platform = str(row.get("platform", "")).strip()
        course_duration = str(row.get("duration", "")).strip()
        course_id = str(row.get("course_id", "")).strip() or build_course_id(platform, title)
        lvl = str(row.get("level", "")).strip()
        g = str(row.get("goal", "")).strip()
        if not (title and platform and course_duration):
            return None
        reason = (
            f"{platform} offering suited to {lvl or 'general'} learners "
            f"with a {g or 'general'} focus."
        )
        return CourseRecommendation(
            course_id=course_id,
            title=title,
            platform=platform,
            duration=course_duration,
            reason=reason,
            source=source,
        )
    except Exception:
        return None


def get_top_dataset_courses(limit: int = 5) -> List[CourseRecommendation]:
    """
    First ``limit`` rows from ``data/courses.json`` as recommendations with ``source='dataset'``.
    """
    rows = load_courses()
    out: List[CourseRecommendation] = []
    for raw in rows:
        if len(out) >= limit:
            break
        if not isinstance(raw, dict):
            continue
        rec = _catalog_row_to_recommendation(raw, source="dataset")
        if rec is not None:
            out.append(rec)
    return out


def retrieve_web_candidates_filtered(query: str) -> List[CourseRecommendation]:
    """
    Fetch public JSON, normalize, keep rows whose title matches query keywords
    (:func:`_query_matches_title`), up to 5. ``source='web'``.
    """
    raw = fetch_courses_from_web()
    if not raw:
        return []
    normalized = map_fetched_courses_to_schema(raw)
    matched: List[CourseRecommendation] = []
    for row in normalized:
        if len(matched) >= 5:
            break
        title = str(row.get("title", ""))
        if not _query_matches_title(query, title):
            continue
        rec = _catalog_row_to_recommendation(dict(row), source="web")
        if rec is not None:
            matched.append(rec)
    return matched


def retrieve_web_candidates_unfiltered(limit: int = 5) -> List[CourseRecommendation]:
    """First ``limit`` normalized rows from the external JSON URL (``source='web'``)."""
    raw = fetch_courses_from_web()
    if not raw:
        return []
    normalized = map_fetched_courses_to_schema(raw)
    out: List[CourseRecommendation] = []
    for row in normalized[:limit]:
        rec = _catalog_row_to_recommendation(dict(row), source="web")
        if rec is not None:
            out.append(rec)
    return out


def retrieve_local_candidates(query_data: Dict[str, str]) -> List[CourseRecommendation]:
    """
    ``data/courses.json`` only: filter by query keywords in title and optional level/goal,
    up to 5 rows (``source='new'``).
    """
    query = query_data.get("query", "").strip()
    level = query_data.get("level", "").strip()
    goal = query_data.get("goal", "").strip()

    rows = load_courses()
    if not rows:
        return []

    matched: List[CourseRecommendation] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title", ""))
        if not _query_matches_title(query, title):
            continue
        if level:
            row_level = str(raw.get("level", "")).strip().lower()
            if row_level != level.lower():
                continue
        if goal:
            row_goal = str(raw.get("goal", "")).strip().lower()
            if row_goal != goal.lower():
                continue
        rec = _catalog_row_to_recommendation(raw, source="new")
        if rec is not None:
            matched.append(rec)
        if len(matched) >= 5:
            break

    return matched


def retrieve_candidates(query_data: Dict[str, str]) -> List[CourseRecommendation]:
    """Alias for :func:`retrieve_local_candidates` (local file only)."""
    return retrieve_local_candidates(query_data)

"""
Decision-based recommendation agent.

Uses enriched query text + Weaviate neighbor similarity to choose:
memory (high match), hybrid (medium), or new (fresh generation).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from config.settings import settings
from db.weaviate_client import search_similar_all
from models.request_models import RecommendRequest
from models.response_models import CourseRecommendation
from services.course_service import fetch_course_search
from services.retriever import merge_dedupe_weaviate_first, parse_stored_courses_from_response
from services.udemy_rapidapi import fetch_udemy_courses
from services.youtube_service import fetch_youtube_courses

logger = logging.getLogger(__name__)

SIM_MEMORY: float = settings.memory_threshold
SIM_HYBRID_FLOOR: float = settings.hybrid_threshold


def _agent_search_text(req: RecommendRequest) -> str:
    """Join non-empty ``query``, ``level``, ``duration``, and ``goal`` for embedding/API search."""
    parts: List[str] = []
    for raw in (req.query, req.level, req.duration, req.goal):
        if raw is None:
            continue
        s = str(raw).strip()
        if s:
            parts.append(s)
    return " ".join(parts).strip()


def fetch_all_courses(query: str) -> List[CourseRecommendation]:
    """Call Udemy, YouTube, and course-search APIs; failures in one source do not block others."""
    q = " ".join((query or "").strip().split())
    if not q:
        return []

    final_results: List[CourseRecommendation] = []

    def safe_add(item: Any, platform: str) -> None:
        if not isinstance(item, dict):
            return
        title = item.get("title") or item.get("name") or "Untitled Course"
        url = item.get("url") or item.get("link") or ""

        course_id = item.get("id")
        if not course_id:
            course_id = f"{platform}_{title}".replace(" ", "_").lower()

        final_results.append(
            CourseRecommendation(
                course_id=str(course_id),
                title=title,
                url=url,
                platform=platform,
                duration="short" if platform == "YouTube" else "medium",
                source="new",
                reason=url if url else f"{platform} course: {title}",
            )
        )

    try:
        for c in fetch_udemy_courses(q):
            safe_add(c, "Udemy")
    except Exception as exc:
        logger.warning("fetch_udemy_courses failed: %s", exc)

    try:
        for c in fetch_youtube_courses(q):
            safe_add(c, "YouTube")
    except Exception as exc:
        logger.warning("fetch_youtube_courses failed: %s", exc)

    try:
        for c in fetch_course_search(q):
            safe_add(c, "Coursera")
    except Exception as exc:
        logger.warning("fetch_course_search failed: %s", exc)

    return final_results


def _hit_similarity(hit: Dict[str, Any]) -> float:
    try:
        return float(hit.get("similarity", 0))
    except (TypeError, ValueError):
        return 0.0


def search_weaviate(query: str) -> tuple[List[CourseRecommendation], float]:
    """
    Embed ``query``, run near-vector search on Weaviate, parse the top neighbor's stored
    ``response`` JSON into courses.

    Returns ``(memory_results, similarity)`` where ``similarity`` is the top hit's score
    (``0.0`` if no hit or on failure).
    """
    q = (query or "").strip()
    if not q:
        return [], 0.0
    try:
        raw = search_similar_all(q, limit=10)
    except Exception as exc:
        logger.exception("search_weaviate: embedding or Weaviate search failed: %s", exc)
        return [], 0.0
    if not raw:
        logger.info("search_weaviate: no neighbors for query=%r", q[:200])
        return [], 0.0
    similarity = _hit_similarity(raw[0])
    response_raw = raw[0].get("response")
    if not isinstance(response_raw, str):
        logger.info("search_weaviate: top hit has no response string similarity=%.4f", similarity)
        return [], similarity
    memory_results = parse_stored_courses_from_response(response_raw, source="memory")
    memory_results = [c.model_copy(update={"source": "memory"}) for c in memory_results]
    logger.info(
        "search_weaviate: similarity=%.4f memory_courses=%d",
        similarity,
        len(memory_results),
    )
    return memory_results, similarity


def fallback_new_recommendations(query_data: RecommendRequest) -> List[CourseRecommendation]:
    """When the main recommender fails, return live API aggregation using full request context."""
    return fetch_all_courses(_agent_search_text(query_data))


def generate_recommendations(query_data: RecommendRequest) -> List[CourseRecommendation]:
    search_text = _agent_search_text(query_data)

    q_lower = query_data.query.lower()
    if "compare" in q_lower or "vs" in q_lower:
        return fetch_all_courses(search_text)

    memory_results, similarity = search_weaviate(search_text)

    if similarity >= SIM_MEMORY:
        return memory_results

    elif SIM_HYBRID_FLOOR <= similarity < SIM_MEMORY:
        api_results = fetch_all_courses(search_text)
        return merge_dedupe_weaviate_first(memory_results, api_results)

    return fetch_all_courses(search_text)

"""
Decision-based recommendation agent.

Weaviate supplies historical context; live APIs (Udemy, YouTube, course-search) always
participate when similarity is above the hybrid floor so results stay multi-source.
"""

from __future__ import annotations

import logging
from typing import Any, List

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


def _api_dict_to_recommendation(item: Any, platform: str) -> CourseRecommendation | None:
    """Normalize one API row to ``CourseRecommendation`` (shared by aggregation and diversity pass)."""
    if not isinstance(item, dict):
        return None
    title = item.get("title") or item.get("name") or "Untitled Course"
    url = item.get("url") or item.get("link") or ""

    course_id = item.get("id")
    if not course_id:
        course_id = f"{platform}_{title}".replace(" ", "_").lower()

    return CourseRecommendation(
        course_id=str(course_id),
        title=title,
        url=url,
        platform=platform,
        duration="short" if platform == "YouTube" else "medium",
        source="new",
        reason=url if url else f"{platform} course: {title}",
    )


def ensure_udemy_diversity(
    candidates: List[CourseRecommendation],
    search_text: str,
    *,
    fetch_limit: int = 3,
) -> List[CourseRecommendation]:
    """If no Udemy listings are present, try a dedicated RapidAPI fetch to reduce single-source bias."""
    st = " ".join((search_text or "").strip().split())
    if not st:
        return candidates
    if any("udemy" in (c.platform or "").lower() for c in candidates):
        return candidates

    seen_ids = {c.course_id for c in candidates}
    seen_urls = {(c.url or "").strip().lower() for c in candidates if (c.url or "").strip()}
    try:
        rows = fetch_udemy_courses(st, limit=fetch_limit)
    except Exception as exc:
        logger.warning("ensure_udemy_diversity: fetch_udemy_courses failed: %s", exc)
        return candidates

    out = list(candidates)
    for item in rows:
        rec = _api_dict_to_recommendation(item, "Udemy")
        if rec is None:
            continue
        u = (rec.url or "").strip().lower()
        if rec.course_id in seen_ids or (u and u in seen_urls):
            continue
        seen_ids.add(rec.course_id)
        if u:
            seen_urls.add(u)
        out.append(rec)

    if len(out) > len(candidates):
        logger.info(
            "ensure_udemy_diversity: injected %d Udemy row(s)",
            len(out) - len(candidates),
        )
    return out


def _finalize_candidates(
    candidates: List[CourseRecommendation],
    search_text: str,
) -> List[CourseRecommendation]:
    return ensure_udemy_diversity(candidates, search_text)


def fetch_all_courses(query: str, *, limit_per_source: int = 15) -> List[CourseRecommendation]:
    """Call Udemy, YouTube, and course-search APIs; failures in one source do not block others."""
    q = " ".join((query or "").strip().split())
    if not q:
        return []

    lim = min(max(limit_per_source, 1), 50)
    final_results: List[CourseRecommendation] = []

    def safe_add(item: Any, platform: str) -> None:
        rec = _api_dict_to_recommendation(item, platform)
        if rec is not None:
            final_results.append(rec)

    try:
        for c in fetch_udemy_courses(q, limit=lim):
            safe_add(c, "Udemy")
    except Exception as exc:
        logger.warning("fetch_udemy_courses failed: %s", exc)

    try:
        for c in fetch_youtube_courses(q)[:lim]:
            safe_add(c, "YouTube")
    except Exception as exc:
        logger.warning("fetch_youtube_courses failed: %s", exc)

    try:
        for c in fetch_course_search(q, limit=lim):
            safe_add(c, "Coursera")
    except Exception as exc:
        logger.warning("fetch_course_search failed: %s", exc)

    return final_results


def _hit_similarity(hit: dict[str, Any]) -> float:
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
        "search_weaviate: similarity=%.4f memory_courses=%d (memory_threshold=%.4f)",
        similarity,
        len(memory_results),
        SIM_MEMORY,
    )
    return memory_results, similarity


def fallback_new_recommendations(query_data: RecommendRequest) -> List[CourseRecommendation]:
    """When the main recommender fails, return live API aggregation using full request context."""
    st = _agent_search_text(query_data)
    return _finalize_candidates(fetch_all_courses(st), st)


def generate_recommendations(query_data: RecommendRequest) -> List[CourseRecommendation]:
    search_text = _agent_search_text(query_data)

    q_lower = query_data.query.lower()
    if "compare" in q_lower or "vs" in q_lower:
        return _finalize_candidates(fetch_all_courses(search_text), search_text)

    memory_results, similarity = search_weaviate(search_text)

    # Parallel hybrid: never return Weaviate-only when we have a neighbor above the hybrid floor.
    if similarity >= SIM_HYBRID_FLOOR and memory_results:
        api_results = fetch_all_courses(search_text)
        merged = merge_dedupe_weaviate_first(memory_results, api_results)
        return _finalize_candidates(merged, search_text)

    return _finalize_candidates(fetch_all_courses(search_text), search_text)

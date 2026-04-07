"""
Decision-based recommendation agent.

Uses enriched query text + Weaviate neighbor similarity to choose:
memory (high match), hybrid (medium), or new (fresh generation).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Set

from db.weaviate_client import search_similar_all
from models.request_models import RecommendRequest
from models.response_models import CourseRecommendation
from services.ranking import rank_courses
from services.retriever import (
    _map_weaviate_to_courses,
    _semantic_search_query,
    get_top_dataset_courses,
    merge_dedupe_weaviate_first,
    parse_stored_courses_from_response,
    retrieve_local_candidates,
    retrieve_web_candidates_filtered,
    retrieve_web_candidates_unfiltered,
)

logger = logging.getLogger(__name__)

# Similarity bands (aligned with search_similar / embedding space).
SIM_MEMORY: float = 0.7
SIM_HYBRID_FLOOR: float = 0.4


def _search_similar(enriched_query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Neighbor search for the enriched query.

    Uses unfiltered results so we can read the true top similarity score
    (``search_similar`` alone applies a threshold and can hide scores).
    On Weaviate or embedding failure, ``search_similar_all`` returns [] (logged in client).
    """
    return search_similar_all(enriched_query, limit=limit)


def _hit_similarity(hit: Dict[str, Any]) -> float:
    try:
        return float(hit.get("similarity", 0))
    except (TypeError, ValueError):
        return 0.0


def _fields(query_data: Dict[str, str]) -> tuple[str, str, str, str]:
    return (
        query_data["query"].strip(),
        query_data["level"].strip(),
        query_data["duration"].strip(),
        query_data["goal"].strip(),
    )


def _with_uniform_source(
    courses: List[CourseRecommendation],
    source: Literal["memory", "new", "dataset", "web"],
) -> List[CourseRecommendation]:
    """Ensure every item uses the same ``source`` for single-origin paths."""
    return [c.model_copy(update={"source": source}) for c in courses]


def _reconcile_hybrid_sources(
    ranked: List[CourseRecommendation],
    weaviate_course_ids: Set[str],
) -> List[CourseRecommendation]:
    """
    After ranking a hybrid merge: Weaviate rows are ``hybrid``; supplemental rows keep
    ``new``, ``dataset``, or ``web`` from the catalog path.
    """
    out: List[CourseRecommendation] = []
    for c in ranked:
        if c.course_id in weaviate_course_ids:
            expected: Literal["hybrid", "new", "dataset", "web"] = "hybrid"
        else:
            expected = c.source
        if c.source != expected:
            c = c.model_copy(update={"source": expected})
        out.append(c)
    return out


def _parse_weaviate_response_json(
    response_json: str,
    source: Literal["memory", "hybrid"],
) -> List[CourseRecommendation]:
    """
    Parse a Weaviate object ``response`` field: a JSON string of a list of course dicts
    into validated ``CourseRecommendation`` structured objects.
    """
    return parse_stored_courses_from_response(response_json, source=source)


def _resolve_catalog_candidates(
    qd: Dict[str, str],
) -> tuple[List[CourseRecommendation], Literal["new", "dataset", "web"]]:
    """
    When Weaviate memory is not used for this response, fill candidates in order:

    1. **Local filtered** — ``retrieve_local_candidates`` (``source`` will be normalized to ``new``).
    2. **Local dataset** — top rows from ``data/courses.json`` (``dataset``).
    3. **External web** — filtered fetch, then unfiltered top 5 if needed (``web``).

    Does not call the separate course-search HTTP API; priority is local → web JSON.
    """
    query, _level, _duration, _goal = _fields(qd)

    local_filtered = retrieve_local_candidates(qd)
    if local_filtered:
        return local_filtered, "new"

    dataset_courses = get_top_dataset_courses(5)
    if dataset_courses:
        return dataset_courses, "dataset"

    web_matched = retrieve_web_candidates_filtered(query)
    if web_matched:
        return web_matched, "web"

    web_any = retrieve_web_candidates_unfiltered(5)
    if web_any:
        return web_any, "web"

    logger.error("No catalog or web data available for recommendations")
    return [], "new"


def fallback_new_recommendations(query_data: RecommendRequest) -> List[CourseRecommendation]:
    """
    Non-Weaviate paths: local filter → local top slice → external JSON (filtered then unfiltered).
    Ranks and sets ``source`` to ``new``, ``dataset``, or ``web`` so responses are non-empty when
    any tier has data.
    """
    qd = query_data.model_dump()
    courses, origin = _resolve_catalog_candidates(qd)
    if not courses:
        return []
    ranked = rank_courses(
        courses,
        qd,
        top_k=5,
        match_context={"path": "new", "best_similarity": 0.0},
    )
    return _with_uniform_source(ranked, origin)


def _new_path(query_dict: Dict[str, str]) -> List[CourseRecommendation]:
    """Catalog / web candidates when Weaviate has no strong match (see :func:`_resolve_catalog_candidates`)."""
    return fallback_new_recommendations(RecommendRequest(**query_dict))


def _memory_path(hit: Dict[str, Any], query_dict: Dict[str, str], top_similarity: float) -> List[CourseRecommendation]:
    """Parse Weaviate ``response`` JSON into course models (source=memory), then rank."""
    response_raw = hit.get("response")
    if not isinstance(response_raw, str):
        return _new_path(query_dict)
    courses = _parse_weaviate_response_json(response_raw, "memory")
    if not courses:
        return _new_path(query_dict)
    ranked = rank_courses(
        courses,
        query_dict,
        top_k=5,
        match_context={"path": "memory", "best_similarity": top_similarity},
    )
    return _with_uniform_source(ranked, "memory")


def _hybrid_path(
    raw_hits: List[Dict[str, Any]],
    query_dict: Dict[str, str],
    top_similarity: float,
) -> List[CourseRecommendation]:
    """
    1. Take top 2 Weaviate neighbor results (in the hybrid similarity band).
    2. Parse their ``response`` JSON into ``CourseRecommendation`` (source=hybrid).
    3. Merge with catalog / web supplemental ``new``, ``dataset``, or ``web`` candidates.
    4. Dedupe by ``course_id`` (Weaviate rows first).
    5. Rank and return top 5.
    """
    hybrid_rows = [
        r for r in raw_hits if SIM_HYBRID_FLOOR <= _hit_similarity(r) < SIM_MEMORY
    ]
    if not hybrid_rows:
        hybrid_rows = raw_hits

    top_two_hits = hybrid_rows[:2]
    stored = _map_weaviate_to_courses(top_two_hits, source="hybrid", max_courses=None)

    qd = query_dict
    fresh, _origin = _resolve_catalog_candidates(qd)
    weaviate_ids = {c.course_id for c in stored}
    merged = merge_dedupe_weaviate_first(stored, fresh)
    if not merged:
        return _new_path(query_dict)
    ranked = rank_courses(
        merged,
        query_dict,
        top_k=5,
        match_context={"path": "hybrid", "best_similarity": top_similarity},
    )
    return _reconcile_hybrid_sources(ranked, weaviate_ids)


def generate_recommendations(query_data: RecommendRequest) -> List[CourseRecommendation]:
    """
    1. Enrich: non-empty query, level, duration, goal (for embedding search)
    2. ``search_similar`` (unfiltered neighbor list via ``search_similar_all``) for scores
    3. Decide: memory / hybrid / new

    Weaviate or embedding failures yield an empty neighbor list → NEW path.
    Any failure while building MEMORY/HYBRID/NEW results falls back to ``fallback_new_recommendations``.
    """
    qd: Dict[str, str] = query_data.model_dump()
    query, level, duration, goal = _fields(qd)
    enriched = _semantic_search_query(query, level, duration, goal)

    raw: List[Dict[str, Any]] = []
    try:
        raw = _search_similar(enriched, limit=10)
    except Exception as exc:
        logger.exception(
            "Unexpected error in neighbor search; falling back to new recommendations: %s",
            exc,
        )
        return fallback_new_recommendations(query_data)

    top_sim = _hit_similarity(raw[0]) if raw else 0.0
    logger.info(
        "agent: enriched_query=%r top_similarity=%.4f",
        enriched,
        top_sim,
    )

    try:
        if not raw or top_sim < SIM_HYBRID_FLOOR:
            logger.info("Agent decision: NEW (no neighbors or similarity below hybrid floor)")
            return _new_path(qd)

        if top_sim >= SIM_MEMORY:
            logger.info("Agent decision: MEMORY")
            return _memory_path(raw[0], qd, top_sim)

        logger.info("Agent decision: HYBRID")
        return _hybrid_path(raw, qd, top_sim)
    except Exception as exc:
        logger.exception(
            "Agent path failed; falling back to catalog/web recommendations: %s",
            exc,
        )
        return fallback_new_recommendations(query_data)

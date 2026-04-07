import logging
from typing import Any, Dict, List, Optional, Tuple

from db.feedback_store import get_average_ratings
from models.response_models import CourseRecommendation

logger = logging.getLogger(__name__)


def _duration_matches(course_duration: str, desired_duration: str) -> bool:
    return desired_duration.strip().lower() in course_duration.strip().lower()


def _level_matches(course_title: str, learner_level: str) -> bool:
    title = course_title.lower()
    lvl = learner_level.lower()

    beginner_keywords = ["beginner", "intro", "foundations", "basics", "getting started"]
    intermediate_keywords = ["intermediate", "practical", "hands-on", "advanced basics"]
    advanced_keywords = ["advanced", "expert", "deep dive", "mastery"]

    keywords_by_level = {
        "beginner": beginner_keywords,
        "intermediate": intermediate_keywords,
        "advanced": advanced_keywords,
    }

    for normalized_level, keywords in keywords_by_level.items():
        if lvl == normalized_level:
            return any(k in title for k in keywords)

    return lvl in title


def _goal_matches(course_title: str, goal: str) -> bool:
    title = course_title.lower()
    g = goal.lower()
    goal_keywords = {
        "job": ["job", "career", "hiring", "interview", "certification"],
        "certification": ["certificate", "certification", "exam", "exam prep"],
        "project": ["project", "portfolio", "build"],
    }

    if g in goal_keywords:
        return any(k in title for k in goal_keywords[g])
    return g in title


def _semantic_score(course: CourseRecommendation, query: str, level: str, duration: str, goal: str) -> float:
    s = 0.0
    if query.lower() in course.title.lower():
        s += 3.0
    if _level_matches(course.title, level):
        s += 3.0
    if _duration_matches(course.duration, duration):
        s += 2.0
    if _goal_matches(course.title, goal):
        s += 2.0
    s += 1.0 if "udemy" in course.platform.lower() else 0.0
    return s


def _final_score(semantic_score: float, feedback_rating: float) -> float:
    """Blend relevance with feedback: SQLite averages and/or ``CourseRecommendation.feedback_score``."""
    return (semantic_score * 0.7) + (feedback_rating * 0.3)


def _combined_feedback_rating(course: CourseRecommendation, sqlite_avg: float) -> float:
    """
    Single signal for ranking: max of live SQLite average and stored ``feedback_score``
    (Weaviate-synced per-course), so memory + new rows in one list rank consistently.
    """
    stored = float(course.feedback_score or 0.0)
    return max(sqlite_avg, stored)


def _build_explanation(
    course: CourseRecommendation,
    query_data: Dict[str, str],
    *,
    semantic_score: float,
    feedback_rating: float,
    path: str,
    best_similarity: float,
) -> str:
    level = query_data["level"]
    duration = query_data["duration"]
    goal = query_data["goal"]
    query = query_data["query"]
    pct = max(0, min(100, int(round(best_similarity * 100))))

    lines: List[str] = []

    if course.source == "memory":
        lines.append(
            f"Returned from stored recommendations with high semantic similarity to your search "
            f"(about {pct}% match on the enriched query in the vector store)."
        )
    elif course.source == "hybrid":
        lines.append(
            f"Drawn from a related stored query (moderate similarity, about {pct}%); "
            f"combined with fresh picks for {level} level and '{goal}' goal."
        )
    elif course.source == "new":
        if path == "hybrid":
            lines.append(
                f"Newly generated suggestion to complement moderate semantic matches, "
                f"aligned with {level} level, {duration}, and '{goal}'."
            )
        else:
            lines.append(
                f"Freshly generated for your topic ({query!r}), {level} level, duration, and '{goal}' goal "
                f"(no strong semantic match in memory)."
            )
    elif course.source == "dataset":
        lines.append(
            f"Picked from the local course catalog (top entries) because filtered matches "
            f"returned no rows for {query!r}."
        )
    elif course.source == "web":
        lines.append(
            f"Sourced from an external public JSON dataset (web fetch) for {query!r}."
        )

    if feedback_rating > 0:
        lines.append(
            f"Feedback signal for ranking is about {feedback_rating:.1f}/5 "
            f"(SQLite averages and/or stored feedback_score).",
        )

    lines.append(
        f"Ranked using relevance (score {semantic_score:.1f}) and feedback (weight 30%)."
    )
    return " ".join(lines)


def rank_courses(
    candidates: List[CourseRecommendation],
    query_data: Dict[str, str],
    top_k: int = 5,
    match_context: Optional[Dict[str, Any]] = None,
) -> List[CourseRecommendation]:
    """
    Score and sort any mixed candidate list (e.g. memory + new, hybrid merge).

    Uses ``_semantic_score`` plus a combined feedback term: max(SQLite avg rating,
    ``course.feedback_score`` from Weaviate JSON).
    """
    level = query_data["level"]
    duration = query_data["duration"]
    goal = query_data["goal"]
    query = query_data["query"]
    ctx = match_context or {"path": "new", "best_similarity": 0.0}
    path = str(ctx.get("path", "new"))
    best_similarity = float(ctx.get("best_similarity", 0.0))

    course_ids = [course.course_id for course in candidates]
    avg_ratings = get_average_ratings(course_ids)

    scored: List[Tuple[CourseRecommendation, float, float, float]] = []
    for course in candidates:
        semantic = _semantic_score(course, query=query, level=level, duration=duration, goal=goal)
        sqlite_avg = avg_ratings.get(course.course_id, 0.0)
        feedback_rating = _combined_feedback_rating(course, sqlite_avg)
        final = _final_score(semantic_score=semantic, feedback_rating=feedback_rating)
        logger.info(
            "ranking course_id=%s semantic_score=%.4f sqlite_avg=%.4f stored_feedback_score=%.4f "
            "feedback_rating=%.4f final_score=%.4f",
            course.course_id,
            semantic,
            sqlite_avg,
            float(course.feedback_score or 0),
            feedback_rating,
            final,
        )
        scored.append((course, semantic, feedback_rating, final))

    scored.sort(key=lambda row: row[3], reverse=True)

    out: List[CourseRecommendation] = []
    for course, semantic, feedback_rating, _ in scored[:top_k]:
        explanation = _build_explanation(
            course,
            query_data,
            semantic_score=semantic,
            feedback_rating=feedback_rating,
            path=path,
            best_similarity=best_similarity,
        )
        out.append(course.model_copy(update={"explanation": explanation}))
    return out

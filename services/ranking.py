import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from db.feedback_store import get_average_ratings
from models.request_models import RecommendRequest
from models.response_models import CourseRecommendation

logger = logging.getLogger(__name__)


def _normalize_level(learner_level: str) -> str:
    s = (learner_level or "").strip().lower()
    if s.startswith("begin") or s == "beginner":
        return "beginner"
    if "intermediate" in s:
        return "intermediate"
    if "advanced" in s:
        return "advanced"
    return s


def _infer_duration_bucket(text: str) -> str:
    """Map free-text duration to short | medium | long for comparing user prefs to listings."""
    t = (text or "").lower()
    if any(x in t for x in ("hour", "week", "day", "minute", "quick", "crash", "1 month", "2 month")):
        return "short"
    if any(x in t for x in ("6 month", "year", "bootcamp", "complete", "comprehensive", "full stack")):
        return "long"
    if "short" in t:
        return "short"
    if "long" in t:
        return "long"
    return "medium"


def _desired_duration_bucket(desired: str) -> str:
    d = (desired or "").lower()
    if any(x in d for x in ("1 month", "2 month", "2 months", "one month", "two month")):
        return "short"
    if any(x in d for x in ("6 month", "6 months", "year", "12 month")):
        return "long"
    if any(x in d for x in ("3 month", "4 month", "5 month", "quarter")):
        return "medium"
    if "flexible" in d or "learning" in d:
        return "medium"
    return "medium"


def _duration_matches(course_duration: str, desired_duration: str) -> bool:
    c = (course_duration or "").strip().lower()
    d = (desired_duration or "").strip().lower()
    if not d:
        return True
    if d in c or c in d:
        return True
    return _infer_duration_bucket(c) == _desired_duration_bucket(d)


def _level_matches(course_title: str, learner_level: str) -> bool:
    title = course_title.lower()
    lvl = _normalize_level(learner_level)

    beginner_keywords = ["beginner", "intro", "foundations", "basics", "getting started", "start", "101"]
    intermediate_keywords = ["intermediate", "practical", "hands-on"]
    advanced_keywords = ["advanced", "expert", "deep dive", "mastery", "professional"]

    keywords_by_level = {
        "beginner": beginner_keywords,
        "intermediate": intermediate_keywords,
        "advanced": advanced_keywords,
    }

    if lvl in keywords_by_level:
        return any(k in title for k in keywords_by_level[lvl])

    return lvl in title


def _goal_matches(course_title: str, goal: str) -> bool:
    title = course_title.lower()
    g = (goal or "").strip().lower()
    if g in ("", "learning", "general", "study"):
        return True
    goal_keywords = {
        "job": ["job", "career", "hiring", "interview", "resume", "professional"],
        "certification": ["certificate", "certification", "exam", "exam prep", "prep"],
        "project": ["project", "portfolio", "build", "hands-on"],
    }

    if g in goal_keywords:
        return any(k in title for k in goal_keywords[g])
    return g in title


def _query_title_overlap(query: str, title: str) -> float:
    """Share of significant query tokens that appear in the title (0–1)."""
    words = [w for w in re.findall(r"[a-z0-9]+", (query or "").lower()) if len(w) >= 3]
    if not words:
        return 0.5 if not (query or "").strip() else 0.0
    tl = title.lower()
    hits = sum(1 for w in words if w in tl)
    return hits / len(words)


def _semantic_score(course: CourseRecommendation, query: str, level: str, duration: str, goal: str) -> float:
    s = 0.0
    overlap = _query_title_overlap(query, course.title)
    s += 1.0 + 5.0 * overlap
    if _level_matches(course.title, level):
        s += 3.0
    if _duration_matches(course.duration, duration):
        s += 2.5
    if _goal_matches(course.title, goal):
        s += 2.0
    s += 2.5 if "udemy" in course.platform.lower() else 0.0
    return s


def build_query_data(payload: RecommendRequest) -> Dict[str, str]:
    return {
        "query": (payload.query or "").strip(),
        "level": (payload.level or "").strip(),
        "duration": (payload.duration or "").strip(),
        "goal": (payload.goal or "").strip(),
    }


def rank_recommendations_for_request(
    candidates: List[CourseRecommendation],
    payload: RecommendRequest,
    *,
    top_k: int = 8,
    match_context: Optional[Dict[str, Any]] = None,
) -> List[CourseRecommendation]:
    """Rank and trim recommendations using query, level, duration, and goal."""
    if not candidates:
        return []
    query_data = build_query_data(payload)
    pool = min(max(top_k * 3, top_k), len(candidates))
    ranked = rank_courses(
        candidates,
        query_data,
        top_k=pool,
        match_context=match_context or {"path": "new", "best_similarity": 0.0},
    )
    return ranked[:top_k]


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
    """Single plain-language line for end users (internal scores kept out of copy)."""
    level = (query_data.get("level") or "").strip() or "your level"
    duration = (query_data.get("duration") or "").strip() or "your timeline"
    goal = (query_data.get("goal") or "").strip() or "your goal"
    query = (query_data.get("query") or "").strip()

    if query:
        short_q = query if len(query) <= 48 else f"{query[:45]}…"
        return (
            f'Relevant to your search ("{short_q}") and a good fit for {level}, '
            f"{duration}, and a {goal}-focused plan."
        )
    return (
        f"Chosen to match your preferences: {level}, {duration}, and a {goal}-oriented goal."
    )


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

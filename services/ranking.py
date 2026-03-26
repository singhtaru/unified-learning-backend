from typing import Dict, List

from models.response_models import CourseRecommendation


def _duration_matches(course_duration: str, desired_duration: str) -> bool:
    # Very lightweight heuristic; future phases can use normalized structured metadata.
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

    # Fallback: substring match for unknown labels.
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


def rank_courses(candidates: List[CourseRecommendation], query_data: Dict[str, str], top_k: int = 5) -> List[CourseRecommendation]:
    """
    Deterministic baseline scoring for Phase 1.
    Placeholder for future ML/vector scoring.
    """
    level = query_data["level"]
    duration = query_data["duration"]
    goal = query_data["goal"]
    query = query_data["query"]

    def score(course: CourseRecommendation) -> int:
        s = 0
        if query.lower() in course.title.lower():
            s += 3
        if _level_matches(course.title, level):
            s += 3
        if _duration_matches(course.duration, duration):
            s += 2
        if _goal_matches(course.title, goal):
            s += 2

        # Encourage platform diversity mildly (reduces ties for consistent output).
        s += 1 if "udemy" in course.platform.lower() else 0
        return s

    sorted_candidates = sorted(candidates, key=score, reverse=True)
    return sorted_candidates[:top_k]


from typing import Dict, List

from models.response_models import CourseRecommendation


def retrieve_candidates(query_data: Dict[str, str]) -> List[CourseRecommendation]:
    """
    Placeholder for future vector DB retrieval (e.g., Weaviate).
    For Phase 1, we return a small curated set of dummy candidates.
    """
    query = query_data["query"].strip()
    level = query_data["level"].strip()
    duration = query_data["duration"].strip()
    goal = query_data["goal"].strip()

    # These are intentionally static/dummy and can later be replaced by vector search results.
    return [
        CourseRecommendation(
            title=f"{query} for Beginners: Foundations and Hands-On Labs",
            platform="Coursera",
            duration=duration,
            reason=f"Matches your {level} level and focuses on {goal}-oriented outcomes.",
        ),
        CourseRecommendation(
            title=f"{query} Essential Skills (Beginner to Intermediate) - Projects Included",
            platform="Udemy",
            duration="2-3 months",
            reason=f"Practical {query} coverage with project practice aligned to your goal: {goal}.",
        ),
        CourseRecommendation(
            title=f"Career Path {query}: Certification Prep and Interview Readiness",
            platform="edX",
            duration="3 months",
            reason="Designed for learners targeting career outcomes like interviews and certification.",
        ),
        CourseRecommendation(
            title=f"{query} Accelerated Learning: Guided Curriculum and Quizzes",
            platform="Pluralsight",
            duration="1-2 months",
            reason=f"A focused course that supports {level} learners with structured practice.",
        ),
        CourseRecommendation(
            title=f"{query} Bootcamp: Build Real Projects and Learn by Doing",
            platform="Udacity",
            duration=duration,
            reason=f"Project-driven learning to help you progress toward your {goal} objective.",
        ),
    ]


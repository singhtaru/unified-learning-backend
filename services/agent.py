from typing import Dict, List

from models.request_models import RecommendRequest
from models.response_models import CourseRecommendation
from services.ranking import rank_courses
from services.retriever import retrieve_candidates


def generate_recommendations(query_data: RecommendRequest) -> List[CourseRecommendation]:
    """
    Mock agent for Phase 1.

    Responsibilities:
    - Retrieve candidate courses (placeholder)
    - Rank candidates (deterministic scoring)
    - Return a structured recommendation list
    """
    # Convert request to a simple dict for downstream services.
    query_dict: Dict[str, str] = query_data.model_dump()

    candidates = retrieve_candidates(query_dict)
    ranked = rank_courses(candidates=candidates, query_data=query_dict, top_k=5)
    return ranked


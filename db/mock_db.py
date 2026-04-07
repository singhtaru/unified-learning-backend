import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from models.request_models import FeedbackType, RecommendRequest
from models.response_models import CourseRecommendation


_LOCK = threading.RLock()

# In-memory storage keyed by query_id. This is a placeholder for Phase 2 DB/vector storage.
_DB: Dict[str, Dict[str, Any]] = {}


def create_query_record(query_id: str, request: RecommendRequest) -> None:
    with _LOCK:
        _DB[query_id] = {
            "request": request.model_dump(),
            "response": None,
            # Aggregate score: helpful => +1, not_helpful => -1 (simple baseline).
            "feedback_score": 0,
            "feedback_count": 0,
            "feedback_history": [],  # list of {"feedback": ..., "timestamp": ...}
            "created_at": datetime.now(timezone.utc).isoformat(),
        }


def store_recommendations(query_id: str, recommendations: List[CourseRecommendation]) -> None:
    with _LOCK:
        if query_id not in _DB:
            raise KeyError(f"Unknown query_id: {query_id}")
        _DB[query_id]["response"] = {"recommendations": [c.model_dump() for c in recommendations]}


def update_feedback(query_id: str, feedback: FeedbackType) -> Tuple[int, int]:
    """
    Updates the aggregate feedback score and count for a given recommendation query.
    Returns: (feedback_score, feedback_count)
    """
    delta = 1 if feedback == FeedbackType.helpful else -1

    with _LOCK:
        if query_id not in _DB:
            raise KeyError(f"Unknown query_id: {query_id}")

        entry = _DB[query_id]
        entry["feedback_score"] += delta
        entry["feedback_count"] += 1
        entry["feedback_history"].append(
            {
                "feedback": feedback.value,
                "delta": delta,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        return entry["feedback_score"], entry["feedback_count"]


def get_feedback_score(query_id: str) -> Optional[Tuple[int, int]]:
    with _LOCK:
        entry = _DB.get(query_id)
        if not entry:
            return None
        return entry["feedback_score"], entry["feedback_count"]


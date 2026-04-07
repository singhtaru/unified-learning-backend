import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, status

from db.feedback_store import get_recent_feedback
from db.weaviate_client import fetch_all_stored_objects

logger = logging.getLogger(__name__)

router = APIRouter(tags=["debug"])


@router.get("/health")
def health() -> Dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


@router.get("/debug/weaviate")
def debug_weaviate() -> Dict[str, Any]:
    """Return all CourseRecommendation objects stored in Weaviate (uuid + properties)."""
    try:
        objects: List[Dict[str, Any]] = fetch_all_stored_objects()
        return {"count": len(objects), "objects": objects}
    except Exception as exc:
        logger.exception("debug /debug/weaviate failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/debug/feedback")
def debug_feedback() -> Dict[str, Any]:
    """Return the 10 most recent feedback rows from SQLite."""
    try:
        records = get_recent_feedback(limit=10)
        return {"count": len(records), "records": records}
    except Exception as exc:
        logger.exception("debug /debug/feedback failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

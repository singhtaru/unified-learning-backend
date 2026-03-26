import logging
from fastapi import APIRouter, HTTPException, status

from db.mock_db import get_feedback_score, update_feedback
from models.request_models import FeedbackRequest
from models.response_models import FeedbackUpdateResponse


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/feedback", response_model=FeedbackUpdateResponse, status_code=status.HTTP_200_OK)
def provide_feedback(payload: FeedbackRequest) -> FeedbackUpdateResponse:
    """
    Update feedback score for a previous recommendation request.

    Phase 1 behavior:
    - Updates the aggregate feedback score/count in mock DB (in-memory)
    """
    try:
        try:
            score, count = update_feedback(query_id=payload.query_id, feedback=payload.feedback)
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown query_id")

        # Re-read from DB for response consistency.
        existing = get_feedback_score(payload.query_id)
        if existing is None:
            raise HTTPException(status_code=500, detail="Storage inconsistency")

        updated_score, updated_count = existing
        return FeedbackUpdateResponse(
            query_id=payload.query_id,
            feedback_score=updated_score,
            feedback_count=updated_count,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update feedback: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update feedback") from e


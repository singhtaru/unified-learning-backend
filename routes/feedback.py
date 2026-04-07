import logging
from fastapi import APIRouter, HTTPException, status

from db.feedback_store import get_average_rating, save_feedback
from db.weaviate_client import sync_course_feedback_to_weaviate
from models.request_models import CourseFeedbackRequest
from models.response_models import FeedbackSuccessResponse


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/feedback", response_model=FeedbackSuccessResponse, status_code=status.HTTP_201_CREATED)
def submit_feedback(payload: CourseFeedbackRequest) -> FeedbackSuccessResponse:
    """Store per-course user feedback in SQLite."""
    try:
        feedback_id = save_feedback(
            user_id=payload.user_id,
            course_id=payload.course_id,
            rating=payload.rating,
            timestamp=payload.timestamp,
        )
        avg = get_average_rating(payload.course_id)
        weaviate_updated = sync_course_feedback_to_weaviate(payload.course_id)
        if weaviate_updated == 0:
            logger.debug(
                "Weaviate: no objects updated for course_id=%r (offline, empty index, or course not in any stored response)",
                payload.course_id,
            )
        else:
            logger.info(
                "Weaviate: refreshed %d object(s) with SQLite averages for course_id=%r (course avg=%.2f)",
                weaviate_updated,
                payload.course_id,
                avg,
            )

        return FeedbackSuccessResponse(
            success=True,
            feedback_id=feedback_id,
            message="Feedback stored successfully",
            course_average_rating=avg,
            weaviate_objects_updated=weaviate_updated,
        )
    except Exception as e:
        logger.exception("Failed to store feedback: %s", e)
        raise HTTPException(status_code=500, detail="Failed to store feedback") from e

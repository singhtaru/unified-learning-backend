import logging
import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from db.mock_db import create_query_record, store_recommendations
from db.weaviate_client import create_schema, store_recommendation
from models.request_models import RecommendRequest
from models.response_models import RecommendResponse
from services.agent import fallback_new_recommendations, generate_recommendations


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/recommend", response_model=RecommendResponse, status_code=status.HTTP_200_OK)
def recommend(payload: RecommendRequest) -> RecommendResponse:
    """
    Generate course recommendations via the decision agent (memory / hybrid / new),
    then persist to mock DB and Weaviate.
    """
    query_id = str(uuid4())

    try:
        create_query_record(query_id=query_id, request=payload)

        try:
            recommendations = generate_recommendations(payload)
        except Exception as gen_exc:
            logger.exception(
                "generate_recommendations failed; using API fallback: %s",
                gen_exc,
            )
            recommendations = fallback_new_recommendations(payload)

        store_recommendations(query_id=query_id, recommendations=recommendations)
        try:
            logger.info("Persisting recommendations to Weaviate for query=%r", payload.query)
            create_schema()
            store_recommendation(
                query=payload.query,
                response=json.dumps([item.model_dump() for item in recommendations]),
                metadata={
                    "level": payload.level,
                    "duration": payload.duration,
                    "goal": payload.goal,
                    "feedback_score": 0,
                },
            )
        except Exception as weaviate_error:
            logger.warning(
                "Weaviate persist after /recommend failed (response still returned): %s",
                weaviate_error,
                exc_info=True,
            )

        return RecommendResponse(query_id=query_id, recommendations=recommendations)
    except HTTPException:
        raise
    except KeyError as e:
        logger.exception("Unknown query_id while storing recommendations: %s", e)
        raise HTTPException(status_code=500, detail="Internal storage error") from e
    except Exception as e:
        logger.exception("Failed to generate recommendations: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate recommendations") from e

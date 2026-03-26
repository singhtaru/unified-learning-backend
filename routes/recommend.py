import logging
import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from db.mock_db import create_query_record, store_recommendations
from db.weaviate_client import create_schema, store_recommendation
from models.request_models import RecommendRequest
from models.response_models import RecommendResponse
from services.agent import generate_recommendations


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/recommend", response_model=RecommendResponse, status_code=status.HTTP_200_OK)
def recommend(payload: RecommendRequest) -> RecommendResponse:
    """
    Generate course recommendations for a user query.

    Phase 1 behavior:
    - Calls a mock agent (deterministic dummy logic)
    - Returns dummy ranked courses
    - Stores query + response in mock DB (in-memory)
    """
    query_id = str(uuid4())

    try:
        create_query_record(query_id=query_id, request=payload)

        recommendations = generate_recommendations(payload)
        # Store full recommendation list for later feedback correlation.
        store_recommendations(query_id=query_id, recommendations=recommendations)
        # Persist semantic memory in Weaviate using external embeddings.
        # Keep recommendation flow available even if vector DB dependency is missing.
        try:
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
            logger.warning("Weaviate persistence skipped: %s", weaviate_error)

        return RecommendResponse(query_id=query_id, recommendations=recommendations)
    except HTTPException:
        raise
    except KeyError as e:
        logger.exception("Unknown query_id while storing recommendations: %s", e)
        raise HTTPException(status_code=500, detail="Internal storage error") from e
    except Exception as e:
        logger.exception("Failed to generate recommendations: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate recommendations") from e


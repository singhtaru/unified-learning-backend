import logging
import os
from typing import Any, Dict, List, Optional

try:
    import weaviate  # type: ignore
    from weaviate.classes.config import Configure, DataType, Property  # type: ignore
    from weaviate.classes.query import MetadataQuery  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    weaviate = None  # type: ignore
    Configure = None  # type: ignore
    DataType = None  # type: ignore
    Property = None  # type: ignore
    MetadataQuery = None  # type: ignore

from services.embedding import get_embedding


logger = logging.getLogger(__name__)

WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")
WEAVIATE_CLASS_NAME = "CourseRecommendation"
SIMILARITY_THRESHOLD = float(os.getenv("WEAVIATE_SIMILARITY_THRESHOLD", "0.75"))


def connect_to_weaviate() -> Any:
    """Create and validate a Weaviate client connection."""
    if weaviate is None:  # pragma: no cover
        raise RuntimeError("Missing dependency: weaviate-client (import failed)")
    client = weaviate.connect_to_local(
        host=WEAVIATE_URL.replace("http://", "").replace("https://", "").split(":")[0],
        port=int(WEAVIATE_URL.split(":")[-1]) if ":" in WEAVIATE_URL else 8080,
    )
    if not client.is_ready():
        client.close()
        raise RuntimeError("Weaviate is not ready")
    return client


def create_schema() -> None:
    """Create CourseRecommendation collection if it does not exist."""
    if weaviate is None or Configure is None or DataType is None or Property is None:  # pragma: no cover
        raise RuntimeError("Missing dependency: weaviate-client (schema cannot be created)")
    client: Optional[Any] = None
    try:
        client = connect_to_weaviate()
        if client.collections.exists(WEAVIATE_CLASS_NAME):
            return

        client.collections.create(
            name=WEAVIATE_CLASS_NAME,
            vectorizer_config=Configure.Vectorizer.none(),
            properties=[
                Property(name="query", data_type=DataType.TEXT),
                Property(name="response", data_type=DataType.TEXT),
                Property(name="level", data_type=DataType.TEXT),
                Property(name="duration", data_type=DataType.TEXT),
                Property(name="goal", data_type=DataType.TEXT),
                Property(name="feedback_score", data_type=DataType.NUMBER),
            ],
        )
    except Exception as exc:
        logger.exception("Failed to create Weaviate schema: %s", exc)
        raise
    finally:
        if client:
            client.close()


def store_recommendation(
    query: str,
    response: str,
    metadata: Dict[str, Any],
) -> str:
    """Generate query embedding and store recommendation object in Weaviate."""
    client: Optional[Any] = None
    try:
        embedding = get_embedding(query)
        client = connect_to_weaviate()
        collection = client.collections.get(WEAVIATE_CLASS_NAME)

        uuid = collection.data.insert(
            properties={
                "query": query,
                "response": response,
                "level": metadata.get("level", ""),
                "duration": metadata.get("duration", ""),
                "goal": metadata.get("goal", ""),
                "feedback_score": float(metadata.get("feedback_score", 0)),
            },
            vector=embedding,
        )
        return str(uuid)
    except Exception as exc:
        logger.exception("Failed to store recommendation: %s", exc)
        raise
    finally:
        if client:
            client.close()


def search_similar(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Generate embedding and search top similar query results."""
    query_embedding = get_embedding(query)
    return search_similar_queries(query_embedding=query_embedding, limit=limit)


def search_similar_queries(query_embedding: List[float], limit: int = 3) -> List[Dict[str, Any]]:
    """Search top similar vectors above similarity threshold."""
    if weaviate is None or MetadataQuery is None:  # pragma: no cover
        raise RuntimeError("Missing dependency: weaviate-client (search cannot be performed)")
    client: Optional[Any] = None
    try:
        client = connect_to_weaviate()
        collection = client.collections.get(WEAVIATE_CLASS_NAME)

        near_result = collection.query.near_vector(
            near_vector=query_embedding,
            limit=limit,
            return_metadata=MetadataQuery(distance=True),
        )

        results: List[Dict[str, Any]] = []
        for obj in near_result.objects:
            distance = float(obj.metadata.distance or 1.0)
            similarity = 1.0 - distance
            if similarity >= SIMILARITY_THRESHOLD:
                results.append(
                    {
                        "id": str(obj.uuid),
                        "query": obj.properties.get("query"),
                        "response": obj.properties.get("response"),
                        "level": obj.properties.get("level"),
                        "duration": obj.properties.get("duration"),
                        "goal": obj.properties.get("goal"),
                        "feedback_score": obj.properties.get("feedback_score"),
                        "similarity": similarity,
                    }
                )
        return results
    except Exception as exc:
        logger.exception("Failed to search similar queries: %s", exc)
        raise
    finally:
        if client:
            client.close()


def update_feedback(query_id: str, feedback: str) -> float:
    """Update feedback score: +1 for helpful, -1 for not_helpful."""
    if weaviate is None:  # pragma: no cover
        raise RuntimeError("Missing dependency: weaviate-client (feedback cannot be updated)")
    client: Optional[Any] = None
    try:
        client = connect_to_weaviate()
        collection = client.collections.get(WEAVIATE_CLASS_NAME)

        current = collection.query.fetch_object_by_id(query_id)
        if not current:
            raise ValueError(f"Query ID not found: {query_id}")

        existing_score = float(current.properties.get("feedback_score", 0))
        delta = 1.0 if feedback == "helpful" else -1.0
        new_score = existing_score + delta

        collection.data.update(
            uuid=query_id,
            properties={"feedback_score": new_score},
        )
        return new_score
    except Exception as exc:
        logger.exception("Failed to update feedback: %s", exc)
        raise
    finally:
        if client:
            client.close()

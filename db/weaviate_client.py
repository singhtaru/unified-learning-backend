import json
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

from config.settings import settings
from services.embedding import get_embedding


logger = logging.getLogger(__name__)

WEAVIATE_URL = settings.weaviate_url
WEAVIATE_CLASS_NAME = "CourseRecommendation"
SIMILARITY_THRESHOLD = settings.similarity_threshold
# Agent tiers: strong = same as SIMILARITY_THRESHOLD by default; partial band is (PARTIAL, STRONG].
STRONG_MATCH_THRESHOLD = float(os.getenv("WEAVIATE_STRONG_MATCH_THRESHOLD", str(SIMILARITY_THRESHOLD)))
PARTIAL_MATCH_THRESHOLD = float(os.getenv("WEAVIATE_PARTIAL_MATCH_THRESHOLD", "0.45"))


def connect_to_weaviate() -> Any:
    """Create and validate a Weaviate client connection."""
    if weaviate is None:  # pragma: no cover
        raise RuntimeError("Missing dependency: weaviate-client (import failed)")
    # skip_init_checks=True avoids client startup gRPC health checks that can fail locally.
    client = weaviate.connect_to_local(
        host=WEAVIATE_URL.replace("http://", "").replace("https://", "").split(":")[0],
        port=int(WEAVIATE_URL.split(":")[-1]) if ":" in WEAVIATE_URL else 8080,
        skip_init_checks=True,
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

        logger.info("Storing to Weaviate query=%r", query)
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
        logger.info("Successfully stored recommendation in Weaviate uuid=%s", uuid)
        return str(uuid)
    except Exception as exc:
        logger.exception(
            "Failed to store recommendation in Weaviate (query=%r): %s",
            query[:500] if query else "",
            exc,
        )
        raise
    finally:
        if client:
            client.close()


def search_similar(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Generate embedding and search top similar query results."""
    try:
        query_embedding = get_embedding(query)
    except Exception as exc:
        logger.exception(
            "Embedding failed before Weaviate search_similar (limit=%d); returning no results: %s",
            limit,
            exc,
        )
        return []
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

        raw_objects = list(near_result.objects)
        logger.info(
            "search_similar_queries: number of results before filtering=%d (limit=%d, threshold=%.4f)",
            len(raw_objects),
            limit,
            SIMILARITY_THRESHOLD,
        )

        results: List[Dict[str, Any]] = []
        for obj in raw_objects:
            distance = float(obj.metadata.distance or 1.0)
            similarity = 1.0 - distance
            logger.info(
                "search_similar_queries: result uuid=%s similarity=%.6f",
                obj.uuid,
                similarity,
            )
            if similarity > SIMILARITY_THRESHOLD:
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
        logger.exception(
            "Weaviate search_similar_queries failed (limit=%d); returning no results: %s",
            limit,
            exc,
        )
        return []
    finally:
        if client:
            client.close()


def search_similar_queries_all(query_embedding: List[float], limit: int = 10) -> List[Dict[str, Any]]:
    """Near-vector search without similarity threshold; results sorted by similarity descending."""
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
        results.sort(key=lambda r: float(r["similarity"]), reverse=True)
        return results
    except Exception as exc:
        logger.exception(
            "Weaviate search_similar_queries_all failed (limit=%d); returning no results: %s",
            limit,
            exc,
        )
        return []
    finally:
        if client:
            client.close()


def fetch_all_stored_objects() -> List[Dict[str, Any]]:
    """
    Return all objects in the CourseRecommendation collection: ``uuid`` plus ``properties``.

    Used by debug tooling. Paginates internally. Does not include vectors.
    """
    if weaviate is None:  # pragma: no cover
        raise RuntimeError("Missing dependency: weaviate-client (import failed)")
    create_schema()
    client: Optional[Any] = None
    try:
        client = connect_to_weaviate()
        collection = client.collections.get(WEAVIATE_CLASS_NAME)
        out: List[Dict[str, Any]] = []
        offset = 0
        page_size = 100
        while True:
            res = collection.query.fetch_objects(limit=page_size, offset=offset)
            objs = res.objects
            if not objs:
                break
            for obj in objs:
                raw = obj.properties or {}
                props: Dict[str, Any] = {}
                for k, v in dict(raw).items():
                    if isinstance(v, (str, int, float, bool)) or v is None:
                        props[k] = v
                    else:
                        props[k] = str(v)
                out.append({"uuid": str(obj.uuid), "properties": props})
            offset += len(objs)
            if len(objs) < page_size:
                break
        return out
    finally:
        if client:
            client.close()


def search_similar_all(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Embedding search returning all top-k neighbors with scores (for strong/partial/none tiers)."""
    try:
        query_embedding = get_embedding(query)
    except Exception as exc:
        logger.exception(
            "Embedding failed before Weaviate search (limit=%d); returning no results: %s",
            limit,
            exc,
        )
        return []
    return search_similar_queries_all(query_embedding=query_embedding, limit=limit)


def _response_list_if_contains_course_id(
    response_str: str,
    course_id: str,
) -> Optional[List[Any]]:
    """
    Parse ``response`` JSON and return the list only if some entry has this exact ``course_id``.

    Avoids substring checks (e.g. ``\"ab\"`` matching ``\"abc\"``).
    """
    try:
        data = json.loads(response_str)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    target = course_id.strip()
    for item in data:
        if isinstance(item, dict) and str(item.get("course_id", "")).strip() == target:
            return data
    return None


def _apply_sqlite_averages_to_course_list(data: List[Any], avgs: Dict[str, float]) -> float:
    """
    Set ``feedback_score`` on each course dict from SQLite averages (1–5 scale).

    Returns the object-level aggregate: mean of per-course averages for entries that have a ``course_id``.
    """
    for item in data:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("course_id", "")).strip()
        if cid:
            item["feedback_score"] = float(avgs.get(cid, 0.0))
    course_items = [x for x in data if isinstance(x, dict) and str(x.get("course_id", "")).strip()]
    if not course_items:
        return 0.0
    per_course = [float(x.get("feedback_score", 0.0)) for x in course_items]
    return sum(per_course) / len(per_course)


def sync_course_feedback_to_weaviate(course_id: str) -> int:
    """
    After SQLite feedback changes: push current average ratings into Weaviate.

    - Scans ``CourseRecommendation`` objects whose ``response`` JSON array includes this ``course_id``
      (exact match on the ``course_id`` field).
    - For each matching object: updates every listed course's ``feedback_score`` from SQLite
      ``AVG(rating)`` (per course), and sets the object's ``feedback_score`` to the mean of those
      per-course averages.
    """
    if weaviate is None:  # pragma: no cover
        logger.error("weaviate-client not installed; skipping Weaviate feedback sync")
        return 0
    from db.feedback_store import get_average_ratings

    try:
        create_schema()
    except Exception as exc:
        logger.exception("Weaviate create_schema failed during feedback sync: %s", exc)
        return 0

    client: Optional[Any] = None
    updated_count = 0
    try:
        client = connect_to_weaviate()
        collection = client.collections.get(WEAVIATE_CLASS_NAME)
        offset = 0
        page_size = 100
        while True:
            res = collection.query.fetch_objects(limit=page_size, offset=offset)
            objs = res.objects
            if not objs:
                break
            for obj in objs:
                props = obj.properties or {}
                response_str = props.get("response")
                if not isinstance(response_str, str):
                    continue
                data = _response_list_if_contains_course_id(response_str, course_id)
                if data is None:
                    continue

                course_ids_in_response: List[str] = []
                for item in data:
                    if isinstance(item, dict):
                        cid = str(item.get("course_id", "")).strip()
                        if cid:
                            course_ids_in_response.append(cid)
                unique_ids = list(dict.fromkeys(course_ids_in_response))
                avgs = get_average_ratings(unique_ids)
                object_feedback = _apply_sqlite_averages_to_course_list(data, avgs)

                collection.data.update(
                    uuid=str(obj.uuid),
                    properties={
                        "response": json.dumps(data),
                        "feedback_score": float(object_feedback),
                    },
                )
                updated_count += 1
            offset += len(objs)
            if len(objs) < page_size:
                break
        logger.info(
            "sync_course_feedback_to_weaviate: course_id=%r updated_objects=%d",
            course_id,
            updated_count,
        )
        return updated_count
    except Exception as exc:
        logger.exception(
            "Failed to sync course feedback to Weaviate (course_id=%r): %s",
            course_id,
            exc,
        )
        return 0
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

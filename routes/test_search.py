from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db.weaviate_client import create_schema, search_similar


router = APIRouter()


class TestSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)


@router.post("/test-search")
def test_search(payload: TestSearchRequest) -> Dict[str, List[Dict[str, Any]]]:
    """Test route for embedding + vector similarity search."""
    try:
        create_schema()
        results = search_similar(payload.query, limit=3)
        return {"results": results}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

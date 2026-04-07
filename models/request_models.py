from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class FeedbackType(str, Enum):
    helpful = "helpful"
    not_helpful = "not_helpful"


class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User search/query for course recommendations")
    level: str = Field(default="beginner", description="Target learner level (e.g., beginner)")
    duration: str = Field(default="flexible", description="Desired course duration")
    goal: str = Field(default="learning", description="User goal (e.g., job, certification)")

    @model_validator(mode="before")
    @classmethod
    def _coalesce_optional_fields(cls, data: Any) -> Any:
        """Omitted keys, null, or blank strings use defaults (no validation error)."""
        if not isinstance(data, dict):
            return data
        defaults = {"level": "beginner", "duration": "flexible", "goal": "learning"}
        merged = {**defaults, **data}
        for key, default in defaults.items():
            val = merged.get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                merged[key] = default
            elif isinstance(val, str):
                merged[key] = val.strip()
        return merged


class FeedbackRequest(BaseModel):
    query_id: str = Field(..., min_length=1, description="ID returned from /recommend")
    feedback: FeedbackType = Field(..., description="Feedback on recommendation usefulness")


class CourseFeedbackRequest(BaseModel):
    user_id: str = Field(..., min_length=1, description="Unique user identifier")
    course_id: str = Field(..., min_length=1, description="Course identifier")
    rating: int = Field(..., ge=1, le=5, description="Rating between 1 and 5")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Feedback timestamp (UTC by default)",
    )

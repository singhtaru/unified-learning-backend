from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FeedbackType(str, Enum):
    helpful = "helpful"
    not_helpful = "not_helpful"


class RecommendRequest(BaseModel):
    """
    POST ``/recommend`` body (canonical JSON keys):

    - ``query`` — main user input (alias: ``userInput``)
    - ``duration`` — desired pace or length
    - ``level`` — learner level (alias: ``selectedLevel``)
    - ``goal`` — learning intent (alias: ``userGoal``)
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "query": "machine learning",
                    "duration": "8 weeks",
                    "level": "beginner",
                    "goal": "career change",
                }
            ]
        },
    )

    query: str = Field(..., min_length=1, description="User search/query for course recommendations")
    level: str = Field(default="beginner", description="Target learner level (e.g., beginner)")
    duration: str = Field(default="flexible", description="Desired course duration")
    goal: str = Field(default="learning", description="User goal (e.g., job, certification)")

    @model_validator(mode="before")
    @classmethod
    def _coalesce_optional_fields(cls, data: Any) -> Any:
        """Accept frontend aliases; omitted or blank optional fields use defaults."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "userInput" in data and "query" not in data:
            data["query"] = data.pop("userInput")
        if "selectedLevel" in data and "level" not in data:
            data["level"] = data.pop("selectedLevel")
        if "userGoal" in data and "goal" not in data:
            data["goal"] = data.pop("userGoal")

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

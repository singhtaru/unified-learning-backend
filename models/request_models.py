from enum import Enum

from pydantic import BaseModel, Field


class FeedbackType(str, Enum):
    helpful = "helpful"
    not_helpful = "not_helpful"


class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User search/query for course recommendations")
    level: str = Field(..., min_length=1, description="Target learner level (e.g., Beginner)")
    duration: str = Field(..., min_length=1, description="Desired course duration (e.g., 3 months)")
    goal: str = Field(..., min_length=1, description="User goal (e.g., job)")


class FeedbackRequest(BaseModel):
    query_id: str = Field(..., min_length=1, description="ID returned from /recommend")
    feedback: FeedbackType = Field(..., description="Feedback on recommendation usefulness")


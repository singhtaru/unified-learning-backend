from typing import List

from pydantic import BaseModel, Field


class CourseRecommendation(BaseModel):
    title: str = Field(..., min_length=1)
    platform: str = Field(..., min_length=1)
    duration: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class RecommendResponse(BaseModel):
    query_id: str = Field(..., description="ID used for correlating feedback")
    recommendations: List[CourseRecommendation]


class FeedbackUpdateResponse(BaseModel):
    query_id: str
    feedback_score: int
    feedback_count: int


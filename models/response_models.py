from typing import List, Literal

from pydantic import BaseModel, Field


class CourseRecommendation(BaseModel):
    course_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    platform: str = Field(..., min_length=1)
    duration: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    explanation: str = Field(
        default="",
        description="Why this course was recommended (filled by ranking or memory path).",
    )
    feedback_score: float = Field(
        default=0.0,
        ge=0.0,
        description="Per-course feedback signal from Weaviate JSON (e.g. avg rating sync); 0 if unknown.",
    )
    source: Literal["memory", "hybrid", "new", "dataset", "web"] = Field(
        ...,
        description=(
            "memory: from Weaviate hit (high similarity); "
            "hybrid: from Weaviate + supplemental mix; "
            "new: filtered match from local courses.json; "
            "dataset: top entries from local courses.json when filters yield nothing; "
            "web: from external public JSON fetch"
        ),
    )


class RecommendResponse(BaseModel):
    query_id: str = Field(..., description="ID used for correlating feedback")
    recommendations: List[CourseRecommendation]


class FeedbackUpdateResponse(BaseModel):
    query_id: str
    feedback_score: int
    feedback_count: int


class CourseFeedbackResponse(BaseModel):
    feedback_id: int
    user_id: str
    course_id: str
    rating: int
    timestamp: str


class FeedbackSuccessResponse(BaseModel):
    success: bool = True
    feedback_id: int
    message: str = "Feedback stored successfully"
    course_average_rating: float = Field(
        0.0,
        description="SQLite average rating (1–5) for this course after storing feedback; 0 if none.",
    )
    weaviate_objects_updated: int = Field(
        0,
        description="Weaviate objects updated: embedded course list refreshed with per-course averages.",
    )

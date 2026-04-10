from typing import List

from pydantic import BaseModel, Field


class CourseRecommendation(BaseModel):
    course_id: str = Field(..., min_length=1, description="Stable course identifier")
    title: str = Field(..., min_length=1, description="Display title")
    url: str = Field(default="", description="Course or listing URL if known")
    platform: str = Field(..., min_length=1, description="e.g. Udemy, YouTube, Coursera")
    duration: str = Field(..., min_length=1, description="Human-readable length or pace")
    source: str = Field(
        ...,
        min_length=1,
        description="Origin label: memory, hybrid, new, dataset, or web",
    )
    reason: str = Field(..., min_length=1, description="Why this course appears in results")
    explanation: str = Field(
        default="",
        description="Why this course was recommended (filled by ranking or memory path).",
    )
    feedback_score: float = Field(
        default=0.0,
        ge=0.0,
        description="Per-course feedback signal from Weaviate JSON (e.g. avg rating sync); 0 if unknown.",
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

from typing import List, Optional

from pydantic import BaseModel, Field


class UserSignup(BaseModel):
    name: str
    email: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class TrackTimeRequest(BaseModel):
    minutes: int = Field(
        ...,
        ge=1,
        le=24 * 60,
        description="Minutes to add to today's learning total (for dashboard total_hours / goal).",
    )


class TrackActivityRequest(BaseModel):
    """POST /track-activity: increment in-memory weekday counter (no JWT)."""

    email: str = Field(..., min_length=1, description="User email (normalized as store key)")
    action: str = Field(
        ...,
        min_length=1,
        description="Interaction label (e.g. view, click); increments today's count once per call",
    )


class UpdateProfileRequest(BaseModel):
    """POST /update-profile body: identify user by email (must match authenticated session)."""

    email: str = Field(..., min_length=3, description="Account email; must match Bearer token subject")
    bio: Optional[str] = Field(default=None, description="Profile bio; omit to leave unchanged")
    skills: Optional[List[str]] = Field(
        default=None,
        description="Skill list; omit to leave unchanged; send [] to clear",
    )


class ProfileUpdate(BaseModel):
    email: Optional[str] = Field(
        default=None,
        description="DEV ONLY (set AUTH_DEV_FALLBACK_EMAIL=true): user email if Bearer token is omitted.",
    )
    bio: Optional[str] = None
    skills: Optional[List[str]] = Field(
        default=None,
        description="Replaces stored skills when provided (JSON array in DB).",
    )
    profile_pic: Optional[str] = Field(
        default=None,
        description="URL or path to profile image; null clears to unset.",
    )
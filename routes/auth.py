import hashlib
import logging
import sqlite3
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials

from auth.security import (
    bearer_scheme,
    create_access_token,
    get_current_user,
    hash_password,
    resolve_current_user,
    verify_password,
)
from config.settings import settings
from db import realtime_activity_store, user_activity_store, user_courses_store, user_store
from user_models import (
    ProfileUpdate,
    TrackActivityRequest,
    TrackTimeRequest,
    UpdateProfileRequest,
    UserLogin,
    UserSignup,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


def _envelope(
    *,
    success: bool,
    message: str,
    data: Optional[Any] = None,
    status_code: int = status.HTTP_200_OK,
):
    return JSONResponse(
        status_code=status_code,
        content={"success": success, "message": message, "data": data},
    )


@router.post("/signup")
def signup(user: UserSignup):
    if len(user.password) > 72:
        return _envelope(
            success=False,
            message="Password too long (max 72 chars)",
            data=None,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if user_store.get_user_by_email(user.email) is not None:
        return _envelope(
            success=False,
            message="User already exists",
            data=None,
            status_code=status.HTTP_409_CONFLICT,
        )

    try:
        password_hash = hash_password(user.password)
    except Exception as exc:
        logger.exception("Password hashing failed: %s", exc)
        return _envelope(
            success=False,
            message=str(exc),
            data=None,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    try:
        user_id = user_store.create_user(user.name, user.email, password_hash)
    except sqlite3.IntegrityError:
        return _envelope(
            success=False,
            message="User already exists",
            data=None,
            status_code=status.HTTP_409_CONFLICT,
        )

    created = user_store.get_user_by_id(user_id)
    if created is None:
        return _envelope(
            success=False,
            message="Registration failed",
            data=None,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return _envelope(
        success=True,
        message="User registered successfully",
        data={**user_store.public_profile(created), "id": created["id"]},
        status_code=status.HTTP_201_CREATED,
    )


@router.post("/login")
def login(user: UserLogin):
    row = user_store.get_user_by_email(user.email)
    if row is None:
        return _envelope(
            success=False,
            message="User not found",
            data=None,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if not verify_password(user.password, row["password_hash"]):
        return _envelope(
            success=False,
            message="Invalid credentials",
            data=None,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    user_activity_store.touch_login_session(row["email"])

    token = create_access_token(user_id=row["id"], email=row["email"])
    return _envelope(
        success=True,
        message="Login successful",
        data={
            "access_token": token,
            "token_type": "bearer",
            "user": user_store.public_profile(row),
        },
    )


@router.get("/profile")
def get_profile(email: str = Query(..., description="User email to load profile for")):
    """Return persisted profile from SQLite (no JWT). ``GET /profile?email=xyz@gmail.com``."""
    key = email.strip()
    if not key or key.lower() in ("null", "undefined"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "message": "Email required", "data": None},
            media_type="application/json",
        )

    row = user_store.get_user_by_email(key)
    if row is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "User not found", "data": None},
            media_type="application/json",
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"success": True, "data": user_store.public_profile(row)},
        media_type="application/json",
    )


@router.post("/update-profile")
def update_profile(
    request: Request,
    payload: UpdateProfileRequest,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """
    Persist ``bio`` and/or ``skills`` for the user. ``email`` must match the authenticated account.
    Uses the same SQLite store as PUT /profile (durable on EC2 when DB is on persistent storage).
    """
    current = resolve_current_user(request, creds, body_email=payload.email)
    if current["email"].strip().lower() != payload.email.strip().lower():
        return _envelope(
            success=False,
            message="Email does not match authenticated user",
            data=None,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    updates = payload.model_dump(exclude_unset=True)
    updates.pop("email", None)
    if not updates:
        row = user_store.get_user_by_id(current["id"])
        if row is None:
            return _envelope(
                success=False,
                message="User not found",
                data=None,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return _envelope(
            success=True,
            message="Profile unchanged",
            data=user_store.public_profile(row),
        )

    updated = user_store.apply_profile_updates(current["id"], updates)
    if updated is None:
        return _envelope(
            success=False,
            message="User not found",
            data=None,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return _envelope(
        success=True,
        message="Profile updated",
        data=user_store.public_profile(updated),
    )


@router.put("/profile")
def put_profile(
    request: Request,
    payload: ProfileUpdate,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """
    Update profile fields present in the JSON body. Each included field replaces its stored value
    (skills: full list replace, not merge). Response data is always re-read from the database after write.
    """
    current = resolve_current_user(request, creds, body_email=payload.email)
    updates = payload.model_dump(exclude_unset=True)
    updates.pop("email", None)
    updated = user_store.apply_profile_updates(current["id"], updates)
    if updated is None:
        return _envelope(
            success=False,
            message="User not found",
            data=None,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return _envelope(
        success=True,
        message="Profile updated",
        data=user_store.public_profile(updated),
    )


def _save_course_response(
    *,
    success: bool,
    message: str,
    data: Optional[Any],
    status_code: int = status.HTTP_200_OK,
) -> JSONResponse:
    """
    Uniform JSON for ``POST /save-course`` so clients never hit empty bodies or non-JSON errors.
    Always includes ``success``, ``message``, and ``data`` (JSON ``null`` when absent).
    """
    return JSONResponse(
        status_code=status_code,
        content={"success": success, "message": message, "data": data},
        media_type="application/json",
    )


@router.post("/save-course")
def save_course(course: dict = Body(...)):
    """
    Persist an interested course by email (no JWT).

    Every outcome is ``JSONResponse`` with ``{ success, message, data }`` — never ``None``,
    never bare ``HTTPException`` (avoids ``detail``-only JSON and empty error bodies in clients).
    """
    try:
        email = (course.get("email") or "").strip()
        if not email:
            return _save_course_response(
                success=False,
                message="Email required",
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        title = (course.get("title") or course.get("course_title") or "").strip()
        platform = (course.get("platform") or "").strip()
        duration = (course.get("duration") or "").strip()

        if not title:
            return _save_course_response(
                success=False,
                message="Title required",
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if not platform:
            return _save_course_response(
                success=False,
                message="Platform required",
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        link = (course.get("link") or "").strip()
        if not link:
            raw = f"{title}|{platform}|{duration}".encode()
            h = hashlib.sha256(raw).hexdigest()[:32]
            link = f"urn:saved-course:{h}"

        row, created_new = user_courses_store.save_user_course(
            user_email=email,
            course_title=title,
            platform=platform,
            link=link,
            duration=duration,
        )

        if created_new:
            user_activity_store.increment_courses_interested(email, 1)

        logger.info(
            "Saved course email=%r title=%r platform=%r duration=%r",
            email,
            title,
            platform,
            duration,
        )

        realtime_activity_store.record_action(email, action="save_course")

        saved = {
            "id": row["id"],
            "email": row["user_email"],
            "title": row["course_title"],
            "platform": row["platform"],
            "duration": row["duration"],
            "link": row["link"],
            "created_at": row["created_at"],
        }
        return _save_course_response(
            success=True,
            message="Course saved successfully",
            data=saved,
            status_code=status.HTTP_200_OK,
        )
    except Exception as exc:
        logger.exception("save-course failed: %s", exc)
        return _save_course_response(
            success=False,
            message=str(exc),
            data=None,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.post("/track-activity")
def track_activity(payload: TrackActivityRequest):
    """
    Record one interaction for the current weekday (no JWT). Body: ``email``, ``action``.

    Updates the same in-memory store used by ``GET /progress`` and ``POST /save-course``.
    """
    display = payload.email.strip()
    key = display.lower() if display else ""
    if not key or key in ("null", "undefined"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "message": "Valid email required", "data": None},
            media_type="application/json",
        )

    action = (payload.action or "").strip()
    if not action:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "message": "Valid action required", "data": None},
            media_type="application/json",
        )

    realtime_activity_store.record_action(display, action=action)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"success": True, "message": "Activity tracked"},
        media_type="application/json",
    )


@router.get("/history")
def get_history(email: str = Query(..., description="User email whose saved courses to return")):
    """
    Saved \"Interested\" courses for ``email`` (no JWT). Query: ``/history?email=user@gmail.com``.

    Success: ``{ "success": true, "data": [...] }``. Errors: JSON with ``success``, ``message``, ``data``.
    """
    try:
        key = email.strip()
        if not key or key.lower() in ("null", "undefined"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": "Valid email query parameter required (e.g. /history?email=user%40gmail.com)",
                    "data": None,
                },
                media_type="application/json",
            )

        courses = user_courses_store.list_saved_courses_for_user(key)
        items = [user_courses_store.history_item(c) for c in courses]
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"success": True, "data": items},
            media_type="application/json",
        )
    except Exception as exc:
        logger.exception("history failed: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "message": str(exc), "data": None},
            media_type="application/json",
        )


@router.get("/progress")
def get_progress(email: str = Query(..., description="User email; progress from saved interested courses")):
    """
    Dashboard payload from SQLite ``user_courses`` (same source as ``GET /history``), no JWT.
    """
    display = email.strip()
    key = display.lower() if display else ""
    if not key or key in ("null", "undefined"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "message": "Email required", "data": None},
            media_type="application/json",
        )

    rows = user_courses_store.list_saved_courses_for_user(key)
    total_courses = len(rows)
    streak = user_courses_store.streak_days_from_saved_courses(rows)
    activity = realtime_activity_store.get_week_activity(key)
    week_actions = sum(activity)
    courses = [user_courses_store.history_item(r) for r in rows]

    goal_target = 10
    stats = [
        {
            "label": "Courses Saved",
            "value": str(total_courses),
            "subtext": "Total interested courses",
        },
        {
            "label": "Activity",
            "value": str(week_actions),
            "subtext": "Tracked interactions this week",
        },
        {
            "label": "Streak",
            "value": str(streak),
            "subtext": "Days active",
        },
        {
            "label": "Goal",
            "value": str(total_courses),
            "target": str(goal_target),
            "progress": min(100, total_courses * 10),
        },
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "user": {"welcomeMessage": f"Welcome back, {display}"},
            "stats": stats,
            "activity": activity,
            "courses": courses,
        },
        media_type="application/json",
    )


@router.post("/progress/time")
def track_learning_time(
    payload: TrackTimeRequest,
    current: dict = Depends(get_current_user),
):
    """Add minutes to today's total (e.g. end of study session)."""
    user_activity_store.add_time_minutes_today(current["email"], payload.minutes)
    saved_n = user_courses_store.count_saved_courses(current["email"])
    data = user_activity_store.build_progress_payload(
        current["email"],
        saved_courses_count=saved_n,
        daily_goal_minutes=settings.progress_daily_goal_minutes,
        chart_days=settings.progress_activity_chart_days,
    )
    return _envelope(success=True, message="Time recorded", data=data)

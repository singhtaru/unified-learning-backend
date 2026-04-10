"""
Course search via RapidAPI (course-search).
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import logging
import os
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

COURSE_SEARCH_URL = "https://course-search.p.rapidapi.com/search"
RAPIDAPI_HOST = "course-search.p.rapidapi.com"


def _first_str(item: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = item.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("results", "data", "courses", "items", "response"):
            val = payload.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
    return []


def fetch_course_search(query: str, *, limit: int = 5) -> List[Dict[str, str]]:
    """
    Search courses via RapidAPI; returns normalized dicts with string keys
    ``id``, ``title``, ``url``, ``platform``, ``duration`` (same shape as Udemy / YouTube helpers).

    At most ``limit`` rows are returned (clamped to 1–50). On failure or missing key, returns ``[]``.
    """
    api_key = (RAPIDAPI_KEY or "").strip()
    if not api_key:
        logger.warning("RAPIDAPI_KEY is not set; skipping course-search RapidAPI")
        return []

    q = " ".join((query or "").strip().split())
    if not q:
        logger.warning("Empty query; skipping course search")
        return []

    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }
    params = {"query": q}

    try:
        response = requests.get(
            COURSE_SEARCH_URL,
            headers=headers,
            params=params,
            timeout=20.0,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Course search API request failed: %s", exc)
        return []

    try:
        payload: Any = response.json()
    except ValueError as exc:
        logger.warning("Course search API returned invalid JSON: %s", exc)
        return []

    items = _extract_items(payload)
    lim = min(max(limit, 1), 50)
    out: List[Dict[str, str]] = []
    for item in items[:lim]:
        title = _first_str(item, "title", "name", "course_title", "courseTitle", "headline")
        if not title:
            continue
        cid = _first_str(item, "id", "course_id", "courseId", "slug", "uuid")
        if not cid:
            cid = title[:80].lower().replace(" ", "-")

        url = _first_str(item, "url", "link", "course_url", "courseUrl", "href")
        if not url:
            url = ""

        duration = _first_str(
            item,
            "duration",
            "workload",
            "effort",
            "time_commitment",
            "timeCommitment",
            "length",
        )
        if not duration:
            duration = "medium"

        out.append(
            {
                "id": cid,
                "title": title,
                "url": url,
                "platform": "Coursera",
                "duration": duration,
            }
        )

    return out

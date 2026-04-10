"""
YouTube Data API v3 search helper for course-style video discovery.
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import logging
import os
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def fetch_youtube_courses(query: str) -> List[Dict[str, str]]:
    """
    Search YouTube for videos matching ``query`` plus ``" course tutorial"``.

    Each item: string keys ``id``, ``title``, ``url``, ``platform`` (``YouTube``),
    ``duration`` — aligned with Udemy and course-search listing shape.

    On missing key, HTTP errors, or malformed responses, logs and returns ``[]``.
    """
    api_key = (YOUTUBE_API_KEY or "").strip()
    if not api_key:
        logger.warning("YOUTUBE_API_KEY is not set; skipping YouTube search")
        return []

    q = " ".join((query or "").strip().split())
    if not q:
        logger.warning("Empty query; skipping YouTube search")
        return []

    search_q = f"{q} course tutorial"
    params = {
        "part": "snippet",
        "q": search_q,
        "type": "video",
        "maxResults": 10,
        "key": api_key,
    }

    try:
        response = requests.get(
            YOUTUBE_SEARCH_URL,
            params=params,
            timeout=20.0,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("YouTube API request failed: %s", exc)
        return []

    try:
        payload: Dict[str, Any] = response.json()
    except ValueError as exc:
        logger.warning("YouTube API returned invalid JSON: %s", exc)
        return []

    if "error" in payload:
        err = payload.get("error") or {}
        logger.warning(
            "YouTube API error: %s",
            err.get("message", err),
        )
        return []

    items = payload.get("items")
    if not isinstance(items, list):
        logger.warning("YouTube API response missing 'items' list")
        return []

    out: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        id_block = item.get("id")
        if not isinstance(id_block, dict):
            continue
        video_id = id_block.get("videoId")
        if not video_id or not isinstance(video_id, str):
            continue

        snippet = item.get("snippet")
        title = ""
        if isinstance(snippet, dict):
            raw_title = snippet.get("title")
            if raw_title is not None:
                title = str(raw_title).strip()
        if not title:
            title = "YouTube video"

        vid = video_id.strip()
        out.append(
            {
                "id": f"youtube-{vid}",
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "platform": "YouTube",
                "duration": "short",
            }
        )

    return out

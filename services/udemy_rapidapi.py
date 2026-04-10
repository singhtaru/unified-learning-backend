"""
Udemy course search via RapidAPI (udemy-course-api).

Loads ``RAPIDAPI_KEY`` from the environment (``.env`` supported via ``load_dotenv``).
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import logging
import os
import re
from typing import Any, Dict, List

import httpx

from services.course_ids import build_course_id

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

logger = logging.getLogger(__name__)

# Full URL from RapidAPI "Code snippets" (override if your listing uses a different path).
DEFAULT_UDEMY_SEARCH_URL = "https://udemy-course-api.p.rapidapi.com/search"
DEFAULT_RAPIDAPI_HOST = "udemy-course-api.p.rapidapi.com"


def _pick_str(item: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = item.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _infer_duration(item: Dict[str, Any]) -> str:
    """Map common API fields to a short duration string; default for beginners."""
    for key in (
        "content_info",
        "duration",
        "total_duration",
        "time_access",
        "caption",
    ):
        v = item.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()[:120]
    hours = item.get("duration_hours") or item.get("total_hours")
    if hours is not None:
        try:
            h = float(hours)
            return f"~{h:.0f} hours" if h >= 1 else "~1 hour"
        except (TypeError, ValueError):
            pass
    return "varies"


def _resolve_udemy_identity(
    item: Dict[str, Any],
    title: str,
    url_raw: str,
    slug: str,
) -> tuple[str, str]:
    """Stable ``id`` and best-effort ``url`` for merging with other API listings."""
    url = (url_raw or "").strip()
    slug = (slug or "").strip()
    rid = _pick_str(item, "id", "course_id", "courseId", "pk", "numeric_id")
    if rid:
        cid = rid if rid.lower().startswith("udemy-") else f"udemy-{rid}"
    elif slug:
        cid = f"udemy-{slug}"
    elif url:
        m = re.search(r"(?:udemy\.com/)?course/([^/?#]+)", url, re.I)
        if m:
            slug_from_url = m.group(1)
            cid = f"udemy-{slug_from_url}"
        else:
            cid = build_course_id("Udemy", title)
    else:
        cid = build_course_id("Udemy", title)

    if not url and slug:
        url = f"https://www.udemy.com/course/{slug}/"
    return cid, url


def _extract_course_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in (
            "results",
            "data",
            "courses",
            "items",
            "response",
            "course_list",
            "body",
            "content",
            "list",
        ):
            val = payload.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
            if isinstance(val, dict) and isinstance(val.get("courses"), list):
                return [x for x in val["courses"] if isinstance(x, dict)]
    return []


def fetch_udemy_courses(query: str, *, limit: int = 5) -> List[Dict[str, str]]:
    """
    Search Udemy courses on RapidAPI and return a normalized list.

    Each item has string keys: ``id``, ``title``, ``url``, ``platform`` (``Udemy``),
    ``duration`` — same shape as :func:`services.youtube_service.fetch_youtube_courses`
    and :func:`services.course_service.fetch_course_search`.
    """
    q = " ".join((query or "").strip().split())
    if not q:
        return []

    if not RAPIDAPI_KEY:
        logger.warning("RAPIDAPI_KEY is not set; skipping Udemy RapidAPI search")
        return []

    host = os.getenv("RAPIDAPI_UDEMY_HOST", DEFAULT_RAPIDAPI_HOST).strip()
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": host,
    }
    url = os.getenv("RAPIDAPI_UDEMY_URL", DEFAULT_UDEMY_SEARCH_URL).strip()
    lim = min(max(limit, 1), 50)
    # Different RapidAPI listings use different query param names; try a few without spamming duplicate keys.
    param_variants: List[Dict[str, Any]] = [
        {"query": q, "limit": lim},
        {"search": q, "limit": lim},
        {"q": q, "limit": lim},
        {"keyword": q, "limit": lim},
    ]

    payload: Any = None
    last_error: str | None = None
    try:
        with httpx.Client(timeout=20.0) as client:
            for params in param_variants:
                try:
                    response = client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    payload = response.json()
                    items_try = _extract_course_list(payload)
                    if items_try:
                        break
                except Exception as exc:
                    last_error = str(exc)
                    continue
            else:
                if last_error:
                    logger.warning(
                        "Udemy RapidAPI: no usable response for url=%r host=%r (last error: %s). "
                        "Copy the exact URL and X-RapidAPI-Host from RapidAPI; set "
                        "RAPIDAPI_UDEMY_URL / RAPIDAPI_UDEMY_HOST if needed.",
                        url,
                        host,
                        last_error,
                    )
                else:
                    logger.warning(
                        "Udemy RapidAPI: HTTP OK but no course list found in JSON for url=%r. "
                        "Response shape may differ — extend _extract_course_list in udemy_rapidapi.py.",
                        url,
                    )
                return []
    except Exception as exc:
        logger.exception("Udemy RapidAPI request failed: %s", exc)
        return []

    items = _extract_course_list(payload)
    out: List[Dict[str, str]] = []
    for item in items[:limit]:
        title = _pick_str(item, "title", "name", "course_title", "headline")
        if not title:
            continue
        duration = _infer_duration(item)
        url_raw = _pick_str(
            item,
            "url",
            "link",
            "course_url",
            "courseUrl",
            "seo_url",
            "share_url",
            "mobile_url",
        )
        slug = _pick_str(item, "slug", "url_slug", "readable_url")
        listing_id, url = _resolve_udemy_identity(item, title, url_raw, slug)
        out.append(
            {
                "id": listing_id,
                "title": title,
                "url": url,
                "platform": "Udemy",
                "duration": duration,
            }
        )
    return out

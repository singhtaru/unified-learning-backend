"""
Fetch course-like records from a public JSON URL (e.g. GitHub raw datasets).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

DEFAULT_COURSES_JSON_URL = (
    "https://raw.githubusercontent.com/ozlerhakan/mongodb-json-files/master/datasets/courses.json"
)


def fetch_courses_from_web(
    url: str | None = None,
    *,
    timeout: float = 30.0,
) -> List[Dict[str, Any]]:
    """
    GET JSON from a public URL and return a list of course-like dicts.

    On network errors, HTTP errors, or invalid JSON, returns an empty list.
    """
    target = (url or DEFAULT_COURSES_JSON_URL).strip()
    if not target:
        return []

    try:
        response = requests.get(
            target,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("fetch_courses_from_web: request failed for %s: %s", target, exc)
        return []

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        logger.warning("fetch_courses_from_web: invalid JSON from %s: %s", target, exc)
        return []

    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if isinstance(data, dict):
        for key in ("courses", "data", "items", "results"):
            val = data.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]

    logger.warning(
        "fetch_courses_from_web: unexpected JSON root type from %s: %s",
        target,
        type(data).__name__,
    )
    return []

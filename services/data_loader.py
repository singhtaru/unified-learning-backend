"""
Load static course catalog from ``data/courses.json``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_COURSES_PATH = _PROJECT_ROOT / "data" / "courses.json"


def load_courses() -> List[Dict[str, Any]]:
    """
    Read ``data/courses.json`` and return a list of course dicts.

    Returns an empty list if the file is missing, unreadable, or not a JSON array.
    """
    try:
        with open(_COURSES_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        logger.debug("Could not read courses file %s: %s", _COURSES_PATH, exc)
        return []
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON in courses file %s: %s", _COURSES_PATH, exc)
        return []

    if not isinstance(data, list):
        logger.warning("courses.json root must be a JSON array; got %s", type(data).__name__)
        return []

    return data

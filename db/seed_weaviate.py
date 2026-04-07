"""
Sample course recommendations for Weaviate (query + JSON response + metadata + embeddings).

Used by scripts and optional app startup; see WEAVIATE_SEED_ON_STARTUP.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Tuple

from db.weaviate_client import create_schema, store_recommendation
from services.course_ids import build_course_id

logger = logging.getLogger(__name__)


def _course(
    platform: str,
    title: str,
    duration: str,
    reason: str,
) -> Dict[str, Any]:
    cid = build_course_id(platform, title)
    return {
        "course_id": cid,
        "title": title,
        "platform": platform,
        "duration": duration,
        "reason": reason,
        "source": "hybrid",
    }


# Five distinct queries; response is JSON list matching /recommend persistence format.
SAMPLE_ENTRIES: List[Tuple[str, str, Dict[str, Any]]] = [
    (
        "learn Python for data science",
        json.dumps(
            [
                _course(
                    "Coursera",
                    "Python for Data Science: NumPy, Pandas, and Visualization",
                    "2-3 months",
                    "Hands-on intro to Python tooling used in analytics and ML pipelines.",
                )
            ]
        ),
        {"level": "beginner", "duration": "3 months", "goal": "job", "feedback_score": 0},
    ),
    (
        "machine learning fundamentals",
        json.dumps(
            [
                _course(
                    "Coursera",
                    "Machine Learning Specialization: Supervised and Unsupervised Learning",
                    "4 months",
                    "Structured path from linear models to neural nets with graded assignments.",
                ),
                _course(
                    "Udemy",
                    "Hands-On ML with Python and Scikit-Learn",
                    "6 weeks",
                    "Practical projects to build intuition before deeper theory.",
                ),
            ]
        ),
        {"level": "intermediate", "duration": "4 months", "goal": "certification", "feedback_score": 0},
    ),
    (
        "web development React",
        json.dumps(
            [
                _course(
                    "Udemy",
                    "Modern React with Hooks and TypeScript",
                    "2 months",
                    "Build production-style UIs with routing, state, and testing basics.",
                )
            ]
        ),
        {"level": "beginner", "duration": "2 months", "goal": "project", "feedback_score": 0},
    ),
    (
        "cloud AWS certification",
        json.dumps(
            [
                _course(
                    "A Cloud Guru",
                    "AWS Solutions Architect Associate — Full Course",
                    "3 months",
                    "Aligned to exam domains with labs and practice tests.",
                )
            ]
        ),
        {"level": "intermediate", "duration": "3 months", "goal": "certification", "feedback_score": 0},
    ),
    (
        "SQL database design",
        json.dumps(
            [
                _course(
                    "Pluralsight",
                    "Relational Database Design and SQL Mastery",
                    "6 weeks",
                    "Normalization, indexing, and query patterns for real applications.",
                )
            ]
        ),
        {"level": "beginner", "duration": "2 months", "goal": "job", "feedback_score": 0},
    ),
]


def seed_sample_recommendations() -> List[str]:
    """
    Ensure schema exists and insert SAMPLE_ENTRIES into Weaviate.

    Each object stores query text, JSON response, flattened metadata properties,
    and a query embedding vector (via store_recommendation / get_embedding).

    Returns list of inserted object UUID strings.
    """
    create_schema()
    ids: List[str] = []
    for query, response, metadata in SAMPLE_ENTRIES:
        uuid = store_recommendation(query=query, response=response, metadata=metadata)
        ids.append(uuid)
        logger.info("Seeded Weaviate sample query=%r uuid=%s", query, uuid)
    return ids


def maybe_seed_weaviate_on_startup() -> None:
    """Run seed once per process if enabled; failures are logged and do not raise."""
    raw = os.getenv("WEAVIATE_SEED_ON_STARTUP", "true").strip().lower()
    if raw not in ("1", "true", "yes", "on"):
        logger.info("Weaviate sample seed skipped (WEAVIATE_SEED_ON_STARTUP=%r)", raw)
        return
    try:
        ids = seed_sample_recommendations()
        logger.info("Weaviate sample seed complete: %d objects inserted", len(ids))
    except Exception as exc:
        logger.warning("Weaviate sample seed failed (app will continue): %s", exc)

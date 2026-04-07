"""
Insert 5 sample course recommendations into Weaviate (CLI).

Uses the same logic as app startup seeding (db.seed_weaviate).

Usage (from project root):
    py scripts/seed_weaviate_samples.py

Requires Weaviate at WEAVIATE_URL (default http://localhost:8080).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Allow running as a script: project root on sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

from db.seed_weaviate import seed_sample_recommendations  # noqa: E402


def main() -> None:
    ids = seed_sample_recommendations()
    print(f"Inserted {len(ids)} objects:", ids)


if __name__ == "__main__":
    main()

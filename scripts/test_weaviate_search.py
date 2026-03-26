import json
import os
import sys


CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db.weaviate_client import (  # noqa: E402
    create_schema,
    search_similar,
    store_recommendation,
    update_feedback,
)


def main() -> None:
    create_schema()

    query = "I need a beginner-level Python course for data analysis in 2 months"
    response = "Recommended: Python for Data Analysis Bootcamp"
    metadata = {
        "level": "Beginner",
        "duration": "2 months",
        "goal": "Data Analysis",
        "feedback_score": 0,
    }

    query_id = store_recommendation(
        query=query,
        response=response,
        metadata=metadata,
    )

    similar = search_similar(query)
    updated_score = update_feedback(query_id=query_id, feedback="helpful")

    print(json.dumps({"stored_query_id": query_id, "similar_results": similar, "updated_feedback_score": updated_score}, indent=2))


if __name__ == "__main__":
    main()

"""
Drop the ``CourseRecommendation`` collection from Weaviate.

Weaviate Python v4 uses ``client.collections.delete(name)`` (not v3 ``schema.delete_class``).

Run from the project root::

    py clear_weaviate.py
"""

from __future__ import annotations

from db.weaviate_client import WEAVIATE_CLASS_NAME, get_client

if __name__ == "__main__":
    client = get_client()
    try:
        try:
            if client.collections.exists(WEAVIATE_CLASS_NAME):
                client.collections.delete(WEAVIATE_CLASS_NAME)
            print("✅ Weaviate class deleted successfully")
        except Exception as e:
            print("⚠️ Error or already deleted:", e)
    finally:
        client.close()

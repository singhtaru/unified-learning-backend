import re


def build_course_id(platform: str, title: str) -> str:
    """Build a stable, URL-safe course identifier from platform + title."""
    normalized = f"{platform.strip().lower()}-{title.strip().lower()}"
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config.settings import settings
from routes.feedback import router as feedback_router
from routes.recommend import router as recommend_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Start accepting HTTP traffic immediately; run Weaviate sample seed in the background.

    Awaiting the seed before ``yield`` delays Uvicorn startup completion and leaves port 8000
    refusing connections while the embedding model loads and Weaviate inserts run (often several seconds).
    """
    async def _seed_background() -> None:
        try:
            from db.seed_weaviate import maybe_seed_weaviate_on_startup

            await asyncio.to_thread(maybe_seed_weaviate_on_startup)
        except Exception as exc:
            logger.warning("Weaviate startup seed could not run: %s", exc)

    asyncio.create_task(_seed_background())
    yield


def _configure_logging() -> None:
    # Centralized logging configuration for both Uvicorn and the app.
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


_configure_logging()

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Unified Course Recommendation and Learning Decision Support System - Phase 1",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

app.include_router(recommend_router)
app.include_router(feedback_router)


@app.get("/demo")
def course_cards_demo() -> FileResponse:
    """Static course-card UI preview (title, platform + duration badges)."""
    return FileResponse(BASE_DIR / "static" / "course-demo.html", media_type="text/html")

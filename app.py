import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from auth.exceptions import AuthError
from config.settings import settings
from routes.auth import router as auth_router
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
    from db.feedback_store import init_feedback_storage
    from db.user_activity_store import init_user_activity_storage
    from db.user_courses_store import init_user_courses_storage
    from db.user_store import init_users_storage

    init_users_storage()
    init_user_courses_storage()
    init_user_activity_storage()
    init_feedback_storage()

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(recommend_router)
app.include_router(feedback_router)


@app.exception_handler(AuthError)
async def auth_error_handler(_request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": exc.message, "data": None},
    )


@app.get("/demo")
def course_cards_demo() -> FileResponse:
    """Static course-card UI preview (title, platform + duration badges)."""
    return FileResponse(BASE_DIR / "static" / "course-demo.html", media_type="text/html")

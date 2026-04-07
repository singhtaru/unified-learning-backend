import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from routes.debug import router as debug_router
from routes.feedback import router as feedback_router
from routes.recommend import router as recommend_router
from routes.test_search import router as test_search_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run one-time Weaviate sample seed off the event loop; failures are non-fatal."""
    try:
        from db.seed_weaviate import maybe_seed_weaviate_on_startup

        await asyncio.to_thread(maybe_seed_weaviate_on_startup)
    except Exception as exc:
        logger.warning("Weaviate startup seed could not run: %s", exc)
    yield


def _configure_logging() -> None:
    # Centralized logging configuration for both Uvicorn and the app.
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


_configure_logging()

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
app.include_router(test_search_router)
app.include_router(debug_router)

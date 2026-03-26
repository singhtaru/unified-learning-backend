import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from routes.feedback import router as feedback_router
from routes.recommend import router as recommend_router
from routes.test_search import router as test_search_router


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


@app.get("/health")
def health_check():
    return {"status": "ok"}


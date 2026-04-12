# Unified Learning — Backend (FastAPI)

API for the **Unified Course Recommendation and Learning Decision Support System** (Phase 1): course recommendations (Weaviate + live sources), auth, saved courses, activity/progress tracking, and feedback.

## Stack

- **FastAPI** + **Uvicorn**
- **Weaviate** for vector search and recommendation memory
- **sentence-transformers** (default model: `all-MiniLM-L6-v2`) for embeddings
- **SQLite** for users, saved courses, activity, and feedback (`users.db` by default)
- Optional live course data: **Udemy / course search** via **RapidAPI** (`RAPIDAPI_KEY`), **YouTube Data API** (`YOUTUBE_API_KEY`)

## Prerequisites

- Python 3.10+ recommended
- A running **Weaviate** instance (default URL: `http://localhost:8080`)
- API keys in `.env` if you want Udemy/RapidAPI and YouTube results (the app still runs without them, with reduced external results)

## Setup

```bash
cd unified-learning-backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: at minimum set RAPIDAPI_KEY and YOUTUBE_API_KEY if you use those sources.
```

## Environment variables

Copy `.env.example` to `.env`. Notable variables:

| Variable | Purpose |
|----------|---------|
| `RAPIDAPI_KEY` | RapidAPI key for Udemy / course-search integrations |
| `YOUTUBE_API_KEY` | YouTube Data API v3 search |
| `WEAVIATE_URL` | Weaviate base URL (default `http://localhost:8080`) |
| `JWT_SECRET_KEY` | HS256 secret for access tokens; set a strong value in production |
| `AUTH_DEV_FALLBACK_EMAIL` | Local-only dev helper for identity without Bearer token (do not enable in production) |
| `USERS_DB_PATH` | SQLite file path for persistence (e.g. EBS path on EC2) |

Additional tuning (thresholds, model name, optional external `COURSE_SEARCH_API_URL`, progress chart settings) is documented on the fields in `config/settings.py`.

**CORS:** `app.py` currently allows all origins (`allow_origins=["*"]`). `.env.example` mentions `CORS_EXTRA_ORIGINS`; that value is merged into `settings.cors_origins` if you later wire `CORSMiddleware` to `settings` instead of a wildcard.

## Run the API

With Weaviate up and `.env` configured:

```bash
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

- Interactive docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Static course-card demo: [http://127.0.0.1:8000/demo](http://127.0.0.1:8000/demo)

On startup, user/activity/feedback SQLite stores are initialized. Weaviate sample seeding runs **in the background** so the server accepts connections immediately while embeddings and inserts may still be in progress.

## Main HTTP routes

- **`POST /recommend`** — Body: `query`, `duration`, `level`, `goal` (with accepted aliases). Returns ranked recommendations; persists query metadata and stores results in the mock DB and Weaviate where applicable.
- **`POST /feedback`** — Course feedback submission.
- **Auth & learning (under same app, no `/api` prefix)** — `POST /signup`, `POST /login`, `GET /profile`, `POST /update-profile`, `PUT /profile`, `POST /save-course`, `POST /track-activity`, `GET /history`, `GET /progress`, `POST /progress/time`.

Protected routes expect a JWT `Authorization: Bearer <token>` unless `AUTH_DEV_FALLBACK_EMAIL` is enabled for local development.

## Project layout (high level)

- `app.py` — FastAPI app, CORS, routers, lifespan
- `routes/` — `auth`, `recommend`, `feedback`
- `services/` — agent, ranking, retriever, YouTube, RapidAPI/Udemy helpers
- `db/` — SQLite stores, Weaviate client, seeding
- `config/settings.py` — Pydantic settings from environment

## Frontend

Pair this service with the **unified-learning-frontend** Vite app. In local development the frontend typically proxies `/api` to this server on port **8000**.

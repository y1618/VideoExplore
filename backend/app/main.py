import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import admin, videos
from app.services.seed import seed_taxonomy_if_empty


def _safe_scan() -> None:
    from app.services.scanner import scan_and_enqueue

    try:
        result = scan_and_enqueue()
        print(f"[startup] autoscan: {result}")
    except Exception as exc:  # pragma: no cover
        print(f"[startup] autoscan failed: {exc}")


def _ensure_schema() -> None:
    """軽量マイグレーション(既存 DB へのカラム追加)。冪等。"""
    from sqlalchemy import text

    from app.db import engine

    stmts = [
        "ALTER TABLE videos ADD COLUMN IF NOT EXISTS favorite BOOLEAN NOT NULL DEFAULT FALSE",
        "CREATE INDEX IF NOT EXISTS idx_videos_favorite ON videos (favorite)",
        "ALTER TABLE videos ADD COLUMN IF NOT EXISTS delete_marked BOOLEAN NOT NULL DEFAULT FALSE",
        "CREATE INDEX IF NOT EXISTS idx_videos_delete_marked ON videos (delete_marked)",
        "ALTER TABLE videos ADD COLUMN IF NOT EXISTS play_count INTEGER NOT NULL DEFAULT 0",
        """CREATE TABLE IF NOT EXISTS comments (
             id         BIGSERIAL PRIMARY KEY,
             video_id   BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
             text       TEXT NOT NULL,
             hashtags   TEXT[] NOT NULL DEFAULT '{}',
             created_at TIMESTAMPTZ NOT NULL DEFAULT now()
           )""",
        "CREATE INDEX IF NOT EXISTS idx_comments_video ON comments (video_id)",
    ]
    try:
        with engine.begin() as conn:
            for stmt in stmts:
                conn.execute(text(stmt))
    except Exception as exc:  # pragma: no cover
        print(f"[startup] schema migration skipped: {exc}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _ensure_schema()
    try:
        added = seed_taxonomy_if_empty()
        if added:
            print(f"[startup] taxonomy seeded: {added} tags")
    except Exception as exc:  # pragma: no cover
        print(f"[startup] taxonomy seed skipped: {exc}")
    if settings.autoscan:
        threading.Thread(target=_safe_scan, daemon=True).start()
    yield


app = FastAPI(title="VideoExplore API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videos.router)
app.include_router(admin.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}

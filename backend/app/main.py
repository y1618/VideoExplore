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


@asynccontextmanager
async def lifespan(_app: FastAPI):
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

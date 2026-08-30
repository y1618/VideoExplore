import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Video

VIDEO_EXTS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts", ".m2ts",
    ".ts", ".wmv", ".flv", ".3gp", ".mpg", ".mpeg", ".mxf", ".mpe",
}


def scan_and_enqueue() -> dict[str, Any]:
    """VIDEO_DIR を走査し、新規動画を登録して解析キューに入れる。"""
    if not os.path.isdir(settings.video_dir):
        raise FileNotFoundError(f"VIDEO_DIR not found: {settings.video_dir}")

    added_ids: list[int] = []
    db = SessionLocal()
    try:
        for root, dirs, files in os.walk(settings.video_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in VIDEO_EXTS:
                    continue
                full = os.path.join(root, filename)
                rel = os.path.relpath(full, settings.video_dir)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                if st.st_size < 1024:  # 1KB 未満は無視
                    continue
                exists = db.scalar(select(Video.id).where(Video.path == rel))
                if exists:
                    continue
                video = Video(
                    path=rel,
                    filename=filename,
                    dirpath=os.path.dirname(rel) or "",
                    size_bytes=st.st_size,
                    mtime=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
                    status="discovered",
                )
                db.add(video)
                db.flush()
                added_ids.append(video.id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if added_ids:
        from worker.tasks import ingest_video

        for vid in added_ids:
            ingest_video.delay(vid)

    return {"added": len(added_ids), "enqueued": len(added_ids)}

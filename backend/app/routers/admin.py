from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.services.scanner import scan_and_enqueue

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/scan")
def scan():
    """動画フォルダを再スキャンし、新規動画の解析をキューに入れる"""
    try:
        return scan_and_enqueue()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"VIDEO_DIR not found: {settings.video_dir}")


@router.post("/reanalyze")
def reanalyze(db: Session = Depends(get_db)):
    """全動画のタグ付けとキャプション生成を再実行する"""
    from worker.tasks import tag_video

    video_ids = [r[0] for r in db.execute(text("SELECT id FROM videos")).all()]
    for vid in video_ids:
        tag_video.delay(vid)
    return {"enqueued": len(video_ids)}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    rows = db.execute(
        text("SELECT status, COUNT(*) AS n FROM videos GROUP BY status")
    ).all()
    by_status = {r.status: int(r.n) for r in rows}
    total = sum(by_status.values())
    tagged = db.execute(
        text("SELECT COUNT(DISTINCT video_id) FROM video_tags")
    ).scalar() or 0
    described = db.execute(
        text("SELECT COUNT(DISTINCT video_id) FROM scenes")
    ).scalar() or 0
    return {"total": total, "tagged": tagged, "described": described, "byStatus": by_status}

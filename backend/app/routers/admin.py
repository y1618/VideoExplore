from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import needs_proxy, settings
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


@router.post("/proxies")
def generate_proxies(db: Session = Depends(get_db)):
    """ブラウザ再生できないコーデック/コンテナの動画についてプロキシ生成をキューに入れる"""
    from app.config import needs_proxy
    from worker.tasks import generate_proxy

    rows = db.execute(
        text("SELECT id, path, codec FROM videos WHERE proxy_path IS NULL")
    ).all()
    targets = [r.id for r in rows if needs_proxy(r.path, r.codec)]
    for vid in targets:
        generate_proxy.delay(vid)
    return {"enqueued": len(targets)}


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
    rows = db.execute(
        text("SELECT path, codec FROM videos WHERE proxy_path IS NULL")
    ).all()
    proxy_pending = sum(1 for r in rows if needs_proxy(r.path, r.codec))
    return {
        "total": total,
        "tagged": tagged,
        "described": described,
        "proxyPending": proxy_pending,
        "byStatus": by_status,
    }

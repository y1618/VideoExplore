import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.db import get_db
from app.models import Scene, Taxonomy, Video, VideoTag
from app.services.streaming import range_response

router = APIRouter(prefix="/api", tags=["videos"])

CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".ts": "video/mp2t",
    ".mts": "video/mp2t",
    ".m2ts": "video/mp2t",
    ".wmv": "video/x-ms-wmv",
    ".flv": "video/x-flv",
    ".3gp": "video/3gpp",
    ".mpg": "video/mpeg",
    ".mpeg": "video/mpeg",
    ".mxf": "application/mxf",
}


def _serialize(
    video: Video,
    tags: list[dict],
    score: float = 0.0,
    description: Optional[str] = None,
) -> dict:
    return {
        "id": video.id,
        "title": video.filename,
        "path": video.path,
        "status": video.status,
        "error": video.error,
        "duration": video.duration_sec,
        "width": video.width,
        "height": video.height,
        "fps": video.fps,
        "codec": video.codec,
        "size": video.size_bytes,
        "profile": video.profile,
        "score": round(score, 3),
        "tags": tags,
        "description": description,
        "updatedAt": video.updated_at.isoformat() if video.updated_at else None,
    }


def _tags_for(db: Session, video_ids: list[int]) -> dict[int, list[dict]]:
    if not video_ids:
        return {}
    rows = (
        db.execute(
            select(VideoTag)
            .where(VideoTag.video_id.in_(video_ids))
            .order_by(VideoTag.confidence.desc())
        )
        .scalars()
        .all()
    )
    result: dict[int, list[dict]] = {vid: [] for vid in video_ids}
    for row in rows:
        result.setdefault(row.video_id, []).append(
            {"tag": row.tag, "confidence": round(row.confidence, 3), "framesHit": row.frames_hit}
        )
    return result


@router.get("/search")
def search(
    q: str = "",
    page: int = 1,
    page_size: int = 24,
    db: Session = Depends(get_db),
):
    """テキスト検索: タグ(日本語/エイリアス)+ ファイル名のスコアリング。"""
    q = (q or "").strip()
    page = max(1, page)
    page_size = min(96, max(1, page_size))

    matched_tags: list[dict] = []
    scored: list[tuple[int, float]] = []
    total = 0

    if q:
        like = f"%{q}%"
        # タグ名 / エイリアスの一致
        tag_rows = db.execute(
            text(
                """
                SELECT vt.video_id, MAX(vt.confidence) AS conf
                FROM video_tags vt
                JOIN taxonomy t ON t.tag = vt.tag
                WHERE t.tag ILIKE :like
                   OR EXISTS (SELECT 1 FROM unnest(t.aliases) a WHERE a ILIKE :like)
                GROUP BY vt.video_id
                """
            ),
            {"like": like},
        ).all()
        tag_scores = {r.video_id: float(r.conf or 0.0) for r in tag_rows}

        # ファイル名一致
        fn_rows = db.execute(
            text(
                """
                SELECT id, COALESCE(similarity(filename, :q), 0) AS sim
                FROM videos
                WHERE filename ILIKE :like
                """
            ),
            {"q": q, "like": like},
        ).all()
        fn_scores = {r.id: 3.0 + 0.5 * float(r.sim or 0.0) for r in fn_rows}

        # 説明文(VLM)一致
        desc_rows = db.execute(
            text(
                """
                SELECT video_id FROM scenes
                WHERE description_ja ILIKE :like OR description_en ILIKE :like
                """
            ),
            {"like": like},
        ).all()
        desc_scores = {r.video_id: 2.5 for r in desc_rows}

        all_ids = set(tag_scores) | set(fn_scores) | set(desc_scores)
        score_map = {
            vid: (
                fn_scores.get(vid, 0.0)
                + 2.0 * tag_scores.get(vid, 0.0)
                + desc_scores.get(vid, 0.0)
            )
            for vid in all_ids
        }
        scored = sorted(all_ids, key=lambda vid: score_map[vid], reverse=True)
        total = len(scored)
        page_ids = scored[(page - 1) * page_size : page * page_size]

        # 検索語に対応するタグ(ヒント表示用)
        mt = db.execute(
            text(
                """
                SELECT t.tag, COUNT(vt.video_id) AS n
                FROM taxonomy t
                JOIN video_tags vt ON vt.tag = t.tag
                WHERE t.tag ILIKE :like
                   OR EXISTS (SELECT 1 FROM unnest(t.aliases) a WHERE a ILIKE :like)
                GROUP BY t.tag
                ORDER BY n DESC
                LIMIT 8
                """
            ),
            {"like": like},
        ).all()
        matched_tags = [{"tag": r.tag, "count": int(r.n)} for r in mt]
    else:
        total = db.scalar(select(func.count(Video.id))) or 0
        rows = (
            db.query(Video)
            .order_by(Video.updated_at.desc(), Video.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        page_ids = [v.id for v in rows]

    videos = (
        db.query(Video)
        .options(joinedload(Video.tags))
        .filter(Video.id.in_(page_ids))
        .all()
        if page_ids
        else []
    )
    by_id = {v.id: v for v in videos}
    tag_map = _tags_for(db, list(page_ids))

    # 説明文(VLM)を取得
    from app.models import Scene

    scene_map: dict[int, Scene] = {}
    if page_ids:
        for s in db.execute(select(Scene).where(Scene.video_id.in_(page_ids))).scalars():
            scene_map.setdefault(s.video_id, s)

    items = []
    for vid in page_ids:
        v = by_id.get(vid)
        if v is None:
            continue
        score = score_map.get(vid, 0.0) if q else 0.0
        scene = scene_map.get(vid)
        items.append(
            _serialize(
                v,
                tag_map.get(vid, []),
                score,
                description=scene.description_ja if scene else None,
            )
        )

    return {
        "total": total,
        "page": page,
        "pageSize": page_size,
        "query": q,
        "matchedTags": matched_tags,
        "items": items,
    }


@router.get("/videos")
def list_videos(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 24,
    db: Session = Depends(get_db),
):
    page = max(1, page)
    page_size = min(96, max(1, page_size))
    query = db.query(Video)
    if status:
        query = query.filter(Video.status == status)
    total = query.count()
    rows = (
        query.order_by(Video.updated_at.desc(), Video.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    tag_map = _tags_for(db, [v.id for v in rows])
    items = [_serialize(v, tag_map.get(v.id, [])) for v in rows]
    return {"total": total, "page": page, "pageSize": page_size, "items": items}


@router.get("/videos/{video_id}")
def get_video(video_id: int, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    tag_map = _tags_for(db, [video_id])

    from app.models import Scene

    scene = (
        db.execute(select(Scene).where(Scene.video_id == video_id).limit(1))
        .scalars()
        .first()
    )
    item = _serialize(
        video,
        tag_map.get(video_id, []),
        description=scene.description_ja if scene else None,
    )
    item["descriptionEn"] = scene.description_en if scene else None
    item["sceneTags"] = scene.tags if scene else []
    return item


@router.get("/videos/{video_id}/thumb")
def get_thumb(video_id: int, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None or not video.thumbnail_path:
        raise HTTPException(status_code=404, detail="thumbnail not found")
    if not os.path.exists(video.thumbnail_path):
        raise HTTPException(status_code=404, detail="thumbnail file missing")
    return FileResponse(video.thumbnail_path, media_type="image/jpeg")


@router.get("/videos/{video_id}/stream")
def stream_video(video_id: int, request: Request, db: Session = Depends(get_db)):
    """Range 対応の動画ストリーミング(SMB マウントから直読み)"""
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    full_path = os.path.join(settings.video_dir, video.path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="video file missing")

    ext = os.path.splitext(video.path)[1].lower()
    content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
    return range_response(request, full_path, content_type)


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)):
    rows = db.execute(
        text(
            """
            SELECT t.tag, t.category, COUNT(vt.video_id) AS n
            FROM taxonomy t
            LEFT JOIN video_tags vt ON vt.tag = t.tag
            GROUP BY t.tag, t.category
            ORDER BY n DESC, t.tag
            LIMIT 48
            """
        )
    ).all()
    return [
        {"tag": r.tag, "category": r.category, "count": int(r.n)} for r in rows
    ]

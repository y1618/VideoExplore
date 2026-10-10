import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import Text, cast, func, literal, nullslast, select, text
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.db import get_db
from app.models import Comment, Scene, Taxonomy, Video, VideoTag
from app.services.streaming import range_response

router = APIRouter(prefix="/api", tags=["videos"])

HASHTAG_RE = re.compile(r"[#＃]([^\s#＃]+)")


def _parse_hashtags(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in HASHTAG_RE.finditer(text):
        tag = m.group(1).strip()[:64]
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _sync_hashtags(db: Session, video_id: int) -> None:
    """コメントのハッシュタグを taxonomy/video_tags に反映(検索対象化)。"""
    rows = db.execute(select(Comment.hashtags).where(Comment.video_id == video_id)).all()
    desired: set[str] = set()
    for (tags,) in rows:
        desired.update(tags or [])

    current = set(
        db.execute(
            select(VideoTag.tag)
            .join(Taxonomy, Taxonomy.tag == VideoTag.tag)
            .where(VideoTag.video_id == video_id, Taxonomy.category == "user")
        )
        .scalars()
        .all()
    )

    for tag in desired - current:
        if not db.get(Taxonomy, tag):
            db.add(Taxonomy(tag=tag, aliases=[], category="user"))
        if not db.get(VideoTag, (video_id, tag)):
            db.add(VideoTag(video_id=video_id, tag=tag, confidence=1.0, frames_hit=0))
    for tag in current - desired:
        vt = db.get(VideoTag, (video_id, tag))
        if vt:
            db.delete(vt)

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
    from app.services.smbpath import to_unc

    proxy_ready = bool(video.proxy_path and os.path.exists(video.proxy_path))
    return {
        "id": video.id,
        "title": video.filename,
        "path": video.path,
        "smbPath": to_unc(video.path),
        "status": video.status,
        "error": video.error,
        "duration": video.duration_sec,
        "width": video.width,
        "height": video.height,
        "fps": video.fps,
        "codec": video.codec,
        "size": video.size_bytes,
        "profile": video.profile,
        "favorite": bool(video.favorite),
        "deleteMarked": bool(video.delete_marked),
        "playCount": video.play_count or 0,
        "score": round(score, 3),
        "proxyReady": proxy_ready,
        "tags": tags,
        "description": description,
        "updatedAt": video.updated_at.isoformat() if video.updated_at else None,
    }


def _tags_for(db: Session, video_ids: list[int]) -> dict[int, list[dict]]:
    if not video_ids:
        return {}
    rows = (
        db.execute(
            select(VideoTag, Taxonomy.category)
            .join(Taxonomy, Taxonomy.tag == VideoTag.tag)
            .where(VideoTag.video_id.in_(video_ids))
            .order_by(VideoTag.confidence.desc())
        )
        .all()
    )
    result: dict[int, list[dict]] = {vid: [] for vid in video_ids}
    for row, category in rows:
        result.setdefault(row.video_id, []).append(
            {
                "tag": row.tag,
                "confidence": round(row.confidence, 3),
                "framesHit": row.frames_hit,
                "category": category,
            }
        )
    return result


@router.get("/search")
def search(
    q: str = "",
    page: int = 1,
    page_size: int = 24,
    favorite: bool = False,
    deleted: bool = False,
    sort: str = "new",
    seed: int = 0,
    db: Session = Depends(get_db),
):
    """テキスト検索: タグ(日本語/エイリアス)+ ファイル名のスコアリング。

    deleted=False(既定)は削除マーク済みを除外、True は削除マーク済みのみ返す。
    sort=random はシード付き決定的シャッフル(md5(id+seed) 順、ページング対応)。
    再生数が少ないものを優先する。sort=old はファイル日時の古い順。
    検索語がある場合はスコア順を優先する。
    """
    q = (q or "").strip()
    page = max(1, page)
    page_size = min(96, max(1, page_size))

    matched_tags: list[dict] = []
    scored: list[tuple[int, float]] = []
    total = 0

    fav_ids: set[int] = set()
    if favorite:
        fav_ids = set(
            db.execute(select(Video.id).where(Video.favorite.is_(True))).scalars().all()
        )
    marked_ids: set[int] = set(
        db.execute(select(Video.id).where(Video.delete_marked.is_(True))).scalars().all()
    )

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
        if favorite:
            scored = [vid for vid in scored if vid in fav_ids]
        if deleted:
            scored = [vid for vid in scored if vid in marked_ids]
        else:
            scored = [vid for vid in scored if vid not in marked_ids]
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
        base = db.query(Video)
        if favorite:
            base = base.filter(Video.favorite.is_(True))
        if deleted:
            base = base.filter(Video.delete_marked.is_(True))
        else:
            base = base.filter(Video.delete_marked.is_(False))
        if sort == "random":
            try:
                s = int(seed)
            except (TypeError, ValueError):
                s = 0
            # シード付き決定的シャッフル: md5(id + ":seed") 順(ページングでも順序固定)。
            # 再生数が少ないものを優先し、同数内ではシャッフルする。
            base = base.order_by(
                Video.play_count.asc(),
                func.md5(func.concat(cast(Video.id, Text), literal(f":{s}"))),
                Video.id,
            )
        elif sort == "old":
            # 古い順もファイル日時(mtime)基準(昇順)
            base = base.order_by(Video.mtime.asc(), Video.id.asc())
        else:
            # 新着順はファイル日時(mtime)基準。再生等での updated_at 変動の影響を受けない。
            base = base.order_by(nullslast(Video.mtime.desc()), Video.id.desc())
        total = base.count()
        rows = (
            base.offset((page - 1) * page_size)
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
    favorite: bool = False,
    deleted: bool = False,
    page: int = 1,
    page_size: int = 24,
    db: Session = Depends(get_db),
):
    page = max(1, page)
    page_size = min(96, max(1, page_size))
    query = db.query(Video)
    if status:
        query = query.filter(Video.status == status)
    if favorite:
        query = query.filter(Video.favorite.is_(True))
    if deleted:
        query = query.filter(Video.delete_marked.is_(True))
    else:
        query = query.filter(Video.delete_marked.is_(False))
    total = query.count()
    rows = (
        query.order_by(nullslast(Video.mtime.desc()), Video.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    tag_map = _tags_for(db, [v.id for v in rows])
    items = [_serialize(v, tag_map.get(v.id, [])) for v in rows]
    return {"total": total, "page": page, "pageSize": page_size, "items": items}


@router.get("/videos/random")
def random_video(exclude: Optional[int] = None, db: Session = Depends(get_db)):
    """ランダムに 1 件の動画 ID を返す(削除マーク済みは除外)。"""
    stmt = select(Video.id).where(Video.delete_marked.is_(False))
    if exclude is not None:
        stmt = stmt.where(Video.id != exclude)
    vid = db.scalar(stmt.order_by(func.random()).limit(1))
    if vid is None:
        raise HTTPException(status_code=404, detail="no videos")
    return {"id": vid}


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


class FavoriteBody(BaseModel):
    favorite: Optional[bool] = None


class DeleteMarkBody(BaseModel):
    marked: Optional[bool] = None


class CommentBody(BaseModel):
    text: str


def _comment_serialize(c: Comment) -> dict:
    return {
        "id": c.id,
        "text": c.text,
        "hashtags": c.hashtags or [],
        "createdAt": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/videos/{video_id}/related")
def related_videos(video_id: int, db: Session = Depends(get_db)):
    """同じタグを持つ関連動画(タグの confidence 合計が高い順)。"""
    rows = db.execute(
        text(
            """
            SELECT vt2.video_id AS vid,
                   SUM(vt2.confidence) AS score,
                   COUNT(*) AS shared
            FROM video_tags vt1
            JOIN video_tags vt2
              ON vt2.tag = vt1.tag AND vt2.video_id != vt1.video_id
            JOIN videos v ON v.id = vt2.video_id
            WHERE vt1.video_id = :vid AND v.delete_marked = false
            GROUP BY vt2.video_id
            ORDER BY score DESC, shared DESC, vt2.video_id DESC
            LIMIT 8
            """
        ),
        {"vid": video_id},
    ).all()
    ids = [r.vid for r in rows]
    if not ids:
        return {"total": 0, "page": 1, "pageSize": 8, "items": []}
    videos = db.query(Video).filter(Video.id.in_(ids)).all()
    tag_map = _tags_for(db, ids)
    order = {vid: i for i, vid in enumerate(ids)}
    items = [
        _serialize(v, tag_map.get(v.id, []))
        for v in sorted(videos, key=lambda x: order[x.id])
    ]
    return {"total": len(items), "page": 1, "pageSize": 8, "items": items}


@router.get("/hashtags")
def hashtag_suggestions(q: str = "", limit: int = 8, db: Session = Depends(get_db)):
    """過去に入力されたハッシュタグの候補(使用回数順)。"""
    q = (q or "").lstrip("#＃").strip()
    rows = db.execute(
        text(
            """
            SELECT t.tag, COUNT(vt.video_id) AS n
            FROM taxonomy t
            JOIN video_tags vt ON vt.tag = t.tag
            WHERE t.category = 'user' AND t.tag ILIKE :like
            GROUP BY t.tag
            ORDER BY n DESC, t.tag
            LIMIT :lim
            """
        ),
        {"like": f"%{q}%", "lim": min(200, max(1, limit))},
    ).all()
    return [{"tag": r.tag, "count": int(r.n)} for r in rows]


@router.get("/videos/{video_id}/comments")
def list_comments(video_id: int, db: Session = Depends(get_db)):
    if db.get(Video, video_id) is None:
        raise HTTPException(status_code=404, detail="video not found")
    rows = (
        db.execute(
            select(Comment)
            .where(Comment.video_id == video_id)
            .order_by(Comment.created_at.desc(), Comment.id.desc())
        )
        .scalars()
        .all()
    )
    return [_comment_serialize(c) for c in rows]


@router.post("/videos/{video_id}/comments")
def create_comment(video_id: int, payload: CommentBody, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    body = payload.text.strip()
    if not body:
        raise HTTPException(status_code=422, detail="empty comment")
    comment = Comment(video_id=video_id, text=body, hashtags=_parse_hashtags(body))
    db.add(comment)
    db.flush()
    _sync_hashtags(db, video_id)
    db.commit()
    db.refresh(comment)
    return _comment_serialize(comment)


@router.delete("/videos/{video_id}/comments/{comment_id}")
def delete_comment(video_id: int, comment_id: int, db: Session = Depends(get_db)):
    comment = db.get(Comment, comment_id)
    if comment is None or comment.video_id != video_id:
        raise HTTPException(status_code=404, detail="comment not found")
    db.delete(comment)
    db.flush()
    _sync_hashtags(db, video_id)
    db.commit()
    return {"ok": True}


@router.post("/videos/{video_id}/delete-mark")
def set_delete_mark(
    video_id: int,
    payload: Optional[DeleteMarkBody] = None,
    db: Session = Depends(get_db),
):
    """削除マーク設定。body 省略時は現在値のトグル。"""
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    if payload is not None and payload.marked is not None:
        video.delete_marked = payload.marked
    else:
        video.delete_marked = not video.delete_marked
    db.commit()
    return {"id": video.id, "deleteMarked": video.delete_marked}


@router.post("/videos/{video_id}/favorite")
def set_favorite(
    video_id: int,
    payload: Optional[FavoriteBody] = None,
    db: Session = Depends(get_db),
):
    """お気に入り設定。body 省略時は現在値のトグル。"""
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    if payload is not None and payload.favorite is not None:
        video.favorite = payload.favorite
    else:
        video.favorite = not video.favorite
    db.commit()
    return {"id": video.id, "favorite": video.favorite}


@router.post("/videos/{video_id}/played")
def count_play(video_id: int, db: Session = Depends(get_db)):
    """再生回数を +1(フロントの再生開始時に 1 回呼ぶ)。"""
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    video.play_count = (video.play_count or 0) + 1
    db.commit()
    return {"id": video.id, "playCount": video.play_count}


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
    """Range 対応の動画ストリーミング(SMB マウントから直読み)。

    ブラウザ再生できないコーデックでプロキシがあればプロキシを配信する。
    """
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")

    from app.config import settings, needs_proxy

    full_path = None
    if needs_proxy(video.path, video.codec) and video.proxy_path and os.path.exists(video.proxy_path):
        full_path = video.proxy_path
    if full_path is None:
        full_path = os.path.join(settings.video_dir, video.path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="video file missing")

    ext = os.path.splitext(full_path)[1].lower()
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

import base64
import glob
import json
import os
import shutil
import subprocess
import tempfile

from sqlalchemy import delete, select

from app.config import settings
from app.db import SessionLocal
from app.models import Taxonomy, Video, VideoTag
from worker.celery_app import celery_app

FFPROBE = "ffprobe"
FFMPEG = "ffmpeg"


def _parse_fps(rate: str | None) -> float | None:
    if not rate:
        return None
    try:
        if "/" in rate:
            num, den = rate.split("/", 1)
            num, den = float(num), float(den)
            if den == 0:
                return None
            return num / den
        return float(rate)
    except (TypeError, ValueError):
        return None


def _mark_error(video_id: int, message: str) -> None:
    db = SessionLocal()
    try:
        video = db.get(Video, video_id)
        if video:
            video.status = "error"
            video.error = message[:500]
            db.commit()
    finally:
        db.close()


@celery_app.task(bind=True, name="worker.tasks.ingest_video", max_retries=1)
def ingest_video(self, video_id: int):
    """メタ取得(ffprobe)+ サムネイル生成(CPU)。完了後にGPUタグ解析へ。"""
    db = SessionLocal()
    try:
        video = db.get(Video, video_id)
        if video is None:
            return {"skipped": "not found"}
        full_path = os.path.join(settings.video_dir, video.path)
        if not os.path.exists(full_path):
            video.status = "error"
            video.error = f"file not found: {video.path}"
            db.commit()
            return {"skipped": "file missing"}

        video.status = "processing"
        db.commit()

        # ---- ffprobe ----
        proc = subprocess.run(
            [FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", full_path],
            capture_output=True,
            text=True,
            timeout=300,
        )
        meta = json.loads(proc.stdout or "{}")
        streams = meta.get("streams", [])
        vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
        fmt = meta.get("format", {})

        try:
            duration = float(fmt.get("duration") or vstream.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0.0

        video.duration_sec = duration or None
        video.width = int(vstream.get("width") or 0) or None
        video.height = int(vstream.get("height") or 0) or None
        video.fps = _parse_fps(vstream.get("avg_frame_rate") or vstream.get("r_frame_rate"))
        video.codec = vstream.get("codec_name")

        # ---- サムネイル ----
        thumbs_dir = os.path.join(settings.cache_dir, "thumbs")
        os.makedirs(thumbs_dir, exist_ok=True)
        thumb_path = os.path.join(thumbs_dir, f"{video_id}.jpg")
        ts = min(max(duration * 0.2, 0.5), 30.0) if duration else 1.0
        thumb_proc = subprocess.run(
            [
                FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{ts:.2f}", "-i", full_path,
                "-frames:v", "1", "-vf", "scale='min(640,iw)':-2",
                thumb_path,
            ],
            capture_output=True,
            timeout=300,
        )
        if thumb_proc.returncode == 0 and os.path.exists(thumb_path):
            video.thumbnail_path = thumb_path

        video.status = "ingested"
        video.error = None
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        _mark_error(video_id, str(exc))
        return {"error": str(exc)}
    finally:
        db.close()

    tag_video.delay(video_id)
    return {"ok": video_id}


@celery_app.task(bind=True, name="worker.tasks.tag_video", max_retries=1)
def tag_video(self, video_id: int):
    """SigLIP2 ゼロショットでタグ付け(GPU)。"""
    db = SessionLocal()
    try:
        video = db.get(Video, video_id)
        if video is None:
            return {"skipped": "not found"}
        full_path = os.path.join(settings.video_dir, video.path)
        if not os.path.exists(full_path):
            _mark_error(video_id, "file missing at tag stage")
            return {"skipped": "file missing"}

        taxonomies = db.execute(
            select(Taxonomy).where(Taxonomy.is_active.is_(True))
        ).scalars().all()
        if not taxonomies:
            video.status = "ready"
            db.commit()
            return {"skipped": "no taxonomy"}

        prompts = [(t.aliases[0] if t.aliases else t.tag) for t in taxonomies]

        video.status = "tagging"
        db.commit()
    finally:
        db.close()

    duration = video.duration_sec or 0
    n_frames = max(1, min(settings.frames_per_video, 48))

    tmp_dir = tempfile.mkdtemp(prefix="ve_frames_")
    try:
        # ---- フレーム抽出 ----
        if duration > 0:
            fps_arg = f"{n_frames / max(duration, 0.1):.6f}"
            vf = f"fps={fps_arg},scale=512:-2"
        else:
            vf = "fps=1/10,scale=512:-2"
        subprocess.run(
            [
                FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                "-i", full_path, "-vf", vf, "-frames:v", str(n_frames), "-q:v", "2",
                os.path.join(tmp_dir, "f_%03d.jpg"),
            ],
            capture_output=True,
            timeout=600,
        )
        frame_paths = sorted(glob.glob(os.path.join(tmp_dir, "f_*.jpg")))
        if not frame_paths:
            _mark_error(video_id, "no frames extracted")
            return {"error": "no frames"}

        # VLM キャプション用にキーフレームをキャッシュへ保存
        kf_dir = os.path.join(settings.cache_dir, "frames", str(video_id))
        os.makedirs(kf_dir, exist_ok=True)
        n_kf = max(1, min(settings.caption_frames, len(frame_paths)))
        idxs = [round(i * (len(frame_paths) - 1) / max(1, n_kf - 1)) for i in range(n_kf)] if n_kf > 1 else [len(frame_paths) // 2]
        for i, idx in enumerate(set(idxs)):
            dst = os.path.join(kf_dir, f"kf_{i}.jpg")
            shutil.copyfile(frame_paths[idx], dst)

        # ---- ゼロショット推定 ----
        import numpy as np

        from worker.vision import zero_shot_probs

        probs = zero_shot_probs(frame_paths, prompts)  # (frames, tags) softmax済み
        best = probs.max(axis=0)
        hits = (probs >= settings.tag_threshold).sum(axis=0)

        db = SessionLocal()
        try:
            db.execute(delete(VideoTag).where(VideoTag.video_id == video_id))
            applied = 0
            # 上位タグのみ採用(しきい値以上 & 最大12個)
            order = np.argsort(best)[::-1][:12]
            for i in order:
                if best[i] >= settings.tag_threshold:
                    db.add(
                        VideoTag(
                            video_id=video_id,
                            tag=taxonomies[int(i)].tag,
                            confidence=float(best[i]),
                            frames_hit=int(hits[i]),
                        )
                    )
                    applied += 1
            video = db.get(Video, video_id)
            if video:
                video.status = "ready"
                video.error = None
            db.commit()
            result = {"ok": video_id, "tags": applied}
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        _mark_error(video_id, f"tagging failed: {exc}")
        return {"error": str(exc)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if settings.vlm_enabled:
        caption_video.delay(video_id)
    return result


VLM_PROMPT = """あなたは動画解析アシスタントです。同じ動画から抽出した最大3枚のフレームを渡します。
映像全体を分析し、**必ず次の形式のJSONのみ**を出力してください。前置き・説明・コードブロックは禁止です。

{"description_ja": "映像の具体的な日本語説明(1〜3文)。場所・人物・車両・動作・天候・時間帯・光の状態(影・逆光・暗さ等)を含める",
 "description_en": "English description of the scene (1-3 sentences)",
 "tags": ["日本語タグを5〜10個"],
 "objects": ["主要な被写体(日本語名)"],
 "time_of_day": "朝/昼/夕方/夜/不明 のいずれか",
 "lighting": "影が強い/逆光/順光/人工照明/不明 のいずれか"}"""


def _vlm_chat(image_uris: list[str], prompt: str) -> str:
    import urllib.request

    from app.config import settings

    content: list[dict] = [
        {"type": "image_url", "image_url": {"url": uri}} for uri in image_uris
    ]
    content.append({"type": "text", "text": prompt})
    payload = {
        "model": settings.vlm_model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 800,
        "temperature": 0.2,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        settings.vlm_api_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=900) as res:
        out = json.load(res)
    msg = out["choices"][0]["message"]
    return msg.get("content") or ""


def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"no JSON found: {text[:200]}")
    return json.loads(text[start : end + 1])


@celery_app.task(bind=True, name="worker.tasks.caption_video", max_retries=2, default_retry_delay=20)
def caption_video(self, video_id: int):
    """VLM(vLLM OpenAI互換API)でキーフレームを解析し、説明文を生成。"""
    from app.config import settings

    if not settings.vlm_enabled:
        return {"skipped": "vlm disabled"}

    kf_dir = os.path.join(settings.cache_dir, "frames", str(video_id))
    kf_paths = sorted(glob.glob(os.path.join(kf_dir, "kf_*.jpg")))
    if not kf_paths:
        return {"skipped": "no keyframes"}

    uris = []
    for p in kf_paths:
        with open(p, "rb") as f:
            uris.append("data:image/jpeg;base64," + base64.b64encode(f.read()).decode())

    parsed = None
    last_err = None
    for attempt in range(2):
        try:
            prompt = VLM_PROMPT if attempt == 0 else (
                VLM_PROMPT + "\n\n注意: 先ほどの出力は不正でした。**JSONのみ**を正確に出力してください。"
            )
            raw = _vlm_chat(uris, prompt)
            parsed = _extract_json(raw)
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    if parsed is None:
        print(f"[caption] video {video_id} failed: {last_err}")
        return {"error": str(last_err)}

    tags = [str(t).strip() for t in parsed.get("tags", []) if str(t).strip()][:10]

    db = SessionLocal()
    try:
        from sqlalchemy import text as sql_text

        from app.models import Scene, Taxonomy

        db.execute(sql_text("DELETE FROM scenes WHERE video_id = :vid"), {"vid": video_id})
        duration = None
        video = db.get(Video, video_id)
        if video:
            duration = video.duration_sec
        db.add(
            Scene(
                video_id=video_id,
                start_sec=0.0,
                end_sec=duration,
                keyframe_path=kf_paths[0],
                description_ja=parsed.get("description_ja"),
                description_en=parsed.get("description_en"),
                tags=tags,
            )
        )
        # VLM のタグも語彙に登録し、video_tags に反映(検索対象にする)
        for tag in tags:
            if not db.get(Taxonomy, tag):
                db.add(Taxonomy(tag=tag, aliases=[], category="VLM"))
            existing = db.get(VideoTag, (video_id, tag))
            if not existing:
                db.add(
                    VideoTag(
                        video_id=video_id,
                        tag=tag,
                        confidence=0.90,
                        frames_hit=0,
                    )
                )
        db.commit()
        return {"ok": video_id, "desc": (parsed.get("description_ja") or "")[:80]}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"[caption] video {video_id} db error: {exc}")
        return {"error": str(exc)}
    finally:
        db.close()

import os
from dataclasses import dataclass


def _env_str(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    database_url: str = _env_str(
        "DATABASE_URL",
        "postgresql+psycopg://videoexplore:videoexplore@db:5432/videoexplore",
    )
    redis_url: str = _env_str("REDIS_URL", "redis://redis:6379/0")

    # コンテナ内のパス(compose でホストの VIDEO_HOST_DIR / CACHE_HOST_DIR をマウント)
    video_dir: str = _env_str("VIDEO_DIR", "/data/videos")
    cache_dir: str = _env_str("CACHE_DIR", "/data/cache")

    # 解析設定
    embed_model: str = _env_str("EMBED_MODEL", "google/siglip2-base-patch16-256")
    tag_threshold: float = _env_float("TAG_THRESHOLD", 0.30)
    frames_per_video: int = _env_int("FRAMES_PER_VIDEO", 12)

    # VLM(vLLM サーバ:ホスト側でポート8888稼働前提)
    vlm_enabled: bool = _env_str("VLM_ENABLED", "true").lower() == "true"
    vlm_api_url: str = _env_str("VLM_API_URL", "http://host.docker.internal:8888/v1")
    vlm_model: str = _env_str("VLM_MODEL", "deepseek-v4-flash-vision-exp")
    caption_frames: int = _env_int("CAPTION_FRAMES", 3)

    # プロキシ生成(720p H.264 + AAC faststart、NVMe キャッシュ)
    proxy_enabled: bool = _env_str("PROXY_ENABLED", "true").lower() == "true"
    proxy_width: int = _env_int("PROXY_WIDTH", 1280)
    proxy_crf: int = _env_int("PROXY_CRF", 23)

    # 起動時挙動
    autoscan: bool = _env_str("AUTOSCAN_ON_STARTUP", "false").lower() == "true"

    # SMB マウント一覧(smbPath 表示用。空なら変換なし)
    smb_mounts_file: str = _env_str("SMB_MOUNTS_FILE", "")


# ブラウザがネイティブ再生できるコーデック(それ以外はプロキシ生成対象)
BROWSER_PLAYABLE_CODECS = frozenset({"h264", "vp8", "vp9", "av1", "av01", "vp09"})
# 同様にネイティブ再生できるコンテナ(FLV等は h264 でもブラウザでは再生不可)
BROWSER_PLAYABLE_EXTS = frozenset({".mp4", ".webm", ".m4v"})


def needs_proxy(path: str, codec: str | None) -> bool:
    """ブラウザで直接再生できない(=プロキシ生成が必要な)動画か判定する。"""
    import os

    ext = os.path.splitext(path)[1].lower()
    if ext not in BROWSER_PLAYABLE_EXTS:
        return True
    return bool(codec and codec not in BROWSER_PLAYABLE_CODECS)


settings = Settings()

"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import Comments from "@/components/Comments";
import VideoCard, { fmtDuration, fmtSize } from "@/components/VideoCard";
import { countPlay, fetchJSON, setDeleteMark, setFavorite, streamUrl, thumbUrl } from "@/lib/api";
import type { ListResponse, VideoItem } from "@/lib/types";

const HISTORY_KEY = "ve_history";

function readHistory(): string[] {
  try {
    const raw = sessionStorage.getItem(HISTORY_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr.map(String) : [];
  } catch {
    return [];
  }
}

export default function WatchPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const router = useRouter();
  const [video, setVideo] = useState<VideoItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [related, setRelated] = useState<VideoItem[]>([]);
  const [nextBusy, setNextBusy] = useState(false);
  const [backHref, setBackHref] = useState("/");
  const videoRef = useRef<HTMLVideoElement>(null);
  const playedRef = useRef(false);
  // ミュート状態をセッションで保持(次の動画/前の動画でも引き継ぐ)
  const [muted, setMuted] = useState(false);

  // 最後の検索状態があれば「検索に戻る」で復元する
  useEffect(() => {
    try {
      const s = sessionStorage.getItem("ve_search");
      if (s) setBackHref(`/?${s}`);
    } catch {}
  }, []);

  useEffect(() => {
    try {
      setMuted(sessionStorage.getItem("ve_muted") === "1");
    } catch {}
  }, []);

  useEffect(() => {
    const el = videoRef.current;
    if (el) el.muted = muted;
  }, [muted, video?.id]);

  // 「検索に戻る」で復元できるようアンカー(どの動画を開いていたか)を記録
  useEffect(() => {
    if (!id) return;
    try {
      sessionStorage.setItem("ve_anchor_id", String(id));
    } catch {}
  }, [id]);

  // 閲覧履歴(「前の動画」用)に現在の動画を記録
  useEffect(() => {
    if (!id) return;
    const hist = readHistory();
    if (hist[hist.length - 1] !== String(id)) {
      hist.push(String(id));
      try {
        sessionStorage.setItem(HISTORY_KEY, JSON.stringify(hist.slice(-100)));
      } catch {}
    }
  }, [id]);

  const goPrev = () => {
    const hist = readHistory();
    const cur = hist.lastIndexOf(String(id));
    if (cur > 0) router.push(`/watch/${hist[cur - 1]}`);
  };

  const hasPrev = (() => {
    const hist = readHistory();
    return hist.lastIndexOf(String(id)) > 0;
  })();

  const goNext = async () => {
    if (nextBusy || !id) return;
    setNextBusy(true);
    try {
      const r = await fetchJSON<{ id: number }>(`/api/videos/random?exclude=${id}`);
      router.push(`/watch/${r.id}`);
    } catch {
      // 候補が無い場合は何もしない
    } finally {
      setNextBusy(false);
    }
  };

  const toggleFavorite = async () => {
    if (!video) return;
    const next = !video.favorite;
    setVideo({ ...video, favorite: next });
    try {
      await setFavorite(video.id, next);
    } catch {
      setVideo({ ...video, favorite: !next });
    }
  };

  const toggleDeleteMark = async () => {
    if (!video) return;
    const next = !video.deleteMarked;
    setVideo({ ...video, deleteMarked: next });
    try {
      await setDeleteMark(video.id, next);
    } catch {
      setVideo({ ...video, deleteMarked: !next });
    }
  };

  const onPlay = () => {
    if (playedRef.current || !video) return;
    playedRef.current = true;
    try {
      sessionStorage.setItem("ve_last_played", String(video.id));
    } catch {}
    countPlay(video.id)
      .then((r) => setVideo((v) => (v ? { ...v, playCount: r.playCount } : v)))
      .catch(() => {});
  };

  const onVolumeChange = () => {
    const el = videoRef.current;
    if (!el) return;
    setMuted(el.muted);
    try {
      sessionStorage.setItem("ve_muted", el.muted ? "1" : "0");
    } catch {}
  };

  const refetchVideo = useCallback(() => {
    if (!id) return;
    fetchJSON<VideoItem>(`/api/videos/${id}`)
      .then(setVideo)
      .catch(() => {});
  }, [id]);

  useEffect(() => {
    if (!id) return;
    fetchJSON<VideoItem>(`/api/videos/${id}`)
      .then(setVideo)
      .catch(() => setError("動画情報の取得に失敗しました"));
    fetchJSON<ListResponse>(`/api/videos/${id}/related`)
      .then((res) => setRelated(res.items))
      .catch(() => {});
  }, [id]);

  // ブラウザ再生できないコーデック/コンテナでプロキシ未生成なら、生成完了をポーリング
  const browserPlayable = (() => {
    if (!video) return true;
    const codecOk =
      !video.codec || ["h264", "vp8", "vp9", "av1", "av01"].includes(video.codec);
    const ext = `.${video.path.split(".").pop()?.toLowerCase() ?? ""}`;
    const containerOk = [".mp4", ".webm", ".m4v"].includes(ext);
    return codecOk && containerOk;
  })();
  useEffect(() => {
    if (!video || browserPlayable || video.proxyReady) return;
    const t = setInterval(refetchVideo, 8000);
    return () => clearInterval(t);
  }, [video, browserPlayable, refetchVideo]);

  // ?t= (秒) で開始位置を指定されたらシークする
  useEffect(() => {
    if (!video) return;
    const t = new URLSearchParams(window.location.search).get("t");
    const el = videoRef.current;
    if (t && el) {
      const seek = () => {
        el.currentTime = parseFloat(t);
      };
      if (el.readyState >= 1) seek();
      else el.addEventListener("loadedmetadata", seek, { once: true });
    }
  }, [video]);

  if (error) {
    return (
      <main className="max-w-3xl mx-auto p-6">
        <Link href="/" className="text-sm text-neutral-400 hover:text-white">
          ← 検索に戻る
        </Link>
        <p className="mt-6 text-red-400">{error}</p>
      </main>
    );
  }

  if (!video) {
    return (
      <main className="max-w-3xl mx-auto p-6">
        <p className="text-neutral-400">読み込み中…</p>
      </main>
    );
  }

  const meta: { label: string; value: string }[] = [
    { label: "長さ", value: fmtDuration(video.duration) || "-" },
    {
      label: "解像度",
      value: video.width && video.height ? `${video.width}×${video.height}` : "-",
    },
    { label: "コーデック", value: video.codec ?? "-" },
    { label: "サイズ", value: fmtSize(video.size) || "-" },
    { label: "再生回数", value: String(video.playCount ?? 0) },
    { label: "ステータス", value: video.status },
  ];

  if (!browserPlayable && video.proxyReady) {
    meta.push({ label: "再生", value: "プロキシ(H.264)" });
  }
  // 縦動画は画面の約80%の高さに制限(スクロール防止)
  const isPortrait =
    video.height != null && video.width != null && video.height > video.width;

  // 項目数に応じて sm 以上で 1 行に収まる列数にする
  const gridCls =
    meta.length >= 7
      ? "grid grid-cols-2 sm:grid-cols-7 gap-2 text-sm"
      : "grid grid-cols-2 sm:grid-cols-6 gap-2 text-sm";

  return (
    <main className="max-w-5xl mx-auto px-4 pb-16">
      <div className="pt-5 flex items-center justify-between gap-2 flex-wrap">
        <Link href={backHref} className="text-sm text-neutral-400 hover:text-white">
          ← 検索に戻る
        </Link>
        <div className="flex gap-2">
          <button
            onClick={goPrev}
            disabled={!hasPrev}
            className="text-sm border border-neutral-700 rounded-lg px-3 py-1.5
                       hover:border-neutral-500 disabled:opacity-40 transition"
          >
            ← 前の動画
          </button>
          <button
            onClick={goNext}
            disabled={nextBusy}
            className="text-sm border border-neutral-700 rounded-lg px-3 py-1.5
                       hover:border-neutral-500 disabled:opacity-40 transition"
          >
            {nextBusy ? "…" : "次の動画 →"}
          </button>
        </div>
      </div>

      <video
        ref={videoRef}
        controls
        autoPlay
        playsInline
        poster={thumbUrl(video.id)}
        src={streamUrl(video.id)}
        onPlay={onPlay}
        onVolumeChange={onVolumeChange}
        className={`mt-3 rounded-xl bg-black ${
          isPortrait ? "mx-auto h-[90vh] w-auto" : "w-full"
        }`}
      />

      <div className="mt-4 flex items-center gap-2">
        <h1 className="text-lg font-semibold">{video.title}</h1>
        <button
          onClick={toggleFavorite}
          aria-label={video.favorite ? "お気に入り解除" : "お気に入り登録"}
          className={`text-xl leading-none transition ${
            video.favorite ? "text-amber-400 hover:text-amber-300" : "text-neutral-600 hover:text-neutral-400"
          }`}
        >
          {video.favorite ? "★" : "☆"}
        </button>
        <button
          onClick={toggleDeleteMark}
          aria-label={video.deleteMarked ? "削除マーク解除" : "削除マークを付ける"}
          title={video.deleteMarked ? "削除マーク済み(クリックで解除)" : "削除マークを付ける"}
          className={`text-sm leading-none transition ${
            video.deleteMarked ? "text-red-500 hover:text-red-400" : "text-neutral-600 hover:text-neutral-400"
          }`}
        >
          🗑
        </button>
        {video.deleteMarked && (
          <span className="text-xs text-red-400">削除マーク済み</span>
        )}
      </div>
      <p className="text-xs text-neutral-500 break-all">{video.smbPath ?? video.path}</p>

      {video.description && (
        <div className="mt-3 rounded-xl bg-neutral-900 ring-1 ring-neutral-800 p-3.5">
          <p className="text-[11px] text-emerald-400 mb-1">VLM による映像解析</p>
          <p className="text-sm leading-relaxed">{video.description}</p>
          {video.descriptionEn && (
            <p className="mt-1.5 text-xs text-neutral-500 leading-relaxed">{video.descriptionEn}</p>
          )}
          {video.sceneTags && video.sceneTags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {video.sceneTags.map((t) => (
                <span key={t} className="text-[11px] bg-neutral-800 text-neutral-300 px-1.5 py-0.5 rounded">
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {video.status !== "ready" && (
        <p className="mt-2 text-xs text-amber-400">
          解析中です(現在: {video.status})。タグは解析完了後に表示されます。
        </p>
      )}
      {!browserPlayable && !video.proxyReady && (
        <p className="mt-2 text-xs text-amber-400">
          このコーデック({video.codec})はブラウザで直接再生できません。プロキシ(H.264)を生成中です。完了次第、自動的に再生できるようになります。
        </p>
      )}
      {!browserPlayable && video.proxyReady && (
        <p className="mt-2 text-xs text-neutral-500">
          プロキシ(H.264)で再生しています。元動画は変更されていません。
        </p>
      )}
      {video.status === "error" && video.error && (
        <p className="mt-2 text-xs text-red-400">解析エラー: {video.error}</p>
      )}

      <div className={`mt-4 ${gridCls}`}>
        {meta.map((m) => (
          <div key={m.label} className="bg-neutral-900 ring-1 ring-neutral-800 rounded-lg p-2.5">
            <p className="text-[11px] text-neutral-500">{m.label}</p>
            <p className="font-medium truncate">{m.value}</p>
          </div>
        ))}
      </div>

      {video.tags.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {video.tags.map((t) => (
            <span
              key={t.tag}
              className="text-xs bg-neutral-800 text-neutral-200 px-2 py-1 rounded-full"
            >
              {t.tag}
              <span className="text-neutral-500"> {Math.round(t.confidence * 100)}%</span>
            </span>
          ))}
        </div>
      )}

      <Comments videoId={video.id} onChanged={refetchVideo} />

      {related.length > 0 && (
        <>
          <h2 className="mt-8 text-sm font-medium text-neutral-400">他の動画</h2>
          <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-4">
            {related.map((item) => (
              <VideoCard key={item.id} item={item} />
            ))}
          </div>
        </>
      )}
    </main>
  );
}

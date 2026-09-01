"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import VideoCard, { fmtDuration, fmtSize } from "@/components/VideoCard";
import { fetchJSON, streamUrl, thumbUrl } from "@/lib/api";
import type { ListResponse, VideoItem } from "@/lib/types";

export default function WatchPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [video, setVideo] = useState<VideoItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [related, setRelated] = useState<VideoItem[]>([]);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!id) return;
    fetchJSON<VideoItem>(`/api/videos/${id}`)
      .then(setVideo)
      .catch(() => setError("動画情報の取得に失敗しました"));
    fetchJSON<ListResponse>(`/api/videos?page=1&page_size=8`)
      .then((res) => setRelated(res.items.filter((v) => String(v.id) !== String(id)).slice(0, 4)))
      .catch(() => {});
  }, [id]);

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
    { label: "ステータス", value: video.status },
  ];

  const browserPlayable = !video.codec || ["h264", "vp8", "vp9", "av01"].includes(video.codec);

  return (
    <main className="max-w-5xl mx-auto px-4 pb-16">
      <div className="pt-5">
        <Link href="/" className="text-sm text-neutral-400 hover:text-white">
          ← 検索に戻る
        </Link>
      </div>

      <video
        ref={videoRef}
        controls
        autoPlay
        playsInline
        poster={thumbUrl(video.id)}
        src={streamUrl(video.id)}
        className="mt-3 w-full rounded-xl bg-black"
      />

      <h1 className="mt-4 text-lg font-semibold">{video.title}</h1>
      <p className="text-xs text-neutral-500 break-all">{video.path}</p>

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
      {!browserPlayable && (
        <p className="mt-2 text-xs text-amber-400">
          このコーデック({video.codec})はブラウザで再生できない可能性があります。
          プロキシ生成(P2)で解消予定です。
        </p>
      )}
      {video.status === "error" && video.error && (
        <p className="mt-2 text-xs text-red-400">解析エラー: {video.error}</p>
      )}

      <div className="mt-4 grid grid-cols-2 sm:grid-cols-5 gap-2 text-sm">
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

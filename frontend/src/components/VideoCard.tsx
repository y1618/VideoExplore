"use client";

import Link from "next/link";
import { useState } from "react";
import { thumbUrl } from "@/lib/api";
import type { VideoItem } from "@/lib/types";

export function fmtDuration(s: number | null): string {
  if (s == null || s <= 0) return "";
  const t = Math.round(s);
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const sec = t % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}

export function fmtSize(bytes: number | null): string {
  if (!bytes) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

const STATUS_LABEL: Record<string, string> = {
  discovered: "待機中",
  processing: "メタ取得中",
  ingested: "解析待ち",
  tagging: "タグ解析中",
  ready: "解析済み",
  error: "エラー",
};

export default function VideoCard({
  item,
  query,
  highlight,
}: {
  item: VideoItem;
  query?: string;
  highlight?: boolean;
}) {
  const [imgOk, setImgOk] = useState(true);
  const topTags = item.tags.slice(0, 4);
  const matched = query ? item.tags.find((t) => t.tag === query) : undefined;

  return (
    <Link
      href={`/watch/${item.id}`}
      data-vid={item.id}
      className={`group block rounded-xl overflow-hidden bg-neutral-900 ring-1 transition ${
        highlight
          ? "ring-2 ring-emerald-400"
          : "ring-neutral-800 hover:ring-emerald-500/60"
      }`}
    >
      <div className="relative aspect-video bg-neutral-800">
        {imgOk && (
          <img
            src={thumbUrl(item.id)}
            alt={item.title}
            loading="lazy"
            onError={() => setImgOk(false)}
            className="absolute inset-0 w-full h-full object-cover group-hover:scale-[1.03] transition duration-200"
          />
        )}
        {!imgOk && (
          <div className="absolute inset-0 flex items-center justify-center text-neutral-600 text-xs">
            サムネイル未生成
          </div>
        )}
        {item.duration != null && item.duration > 0 && (
          <span className="absolute bottom-1.5 right-1.5 text-[11px] bg-black/75 text-white px-1.5 py-0.5 rounded">
            {fmtDuration(item.duration)}
          </span>
        )}
        {(item.favorite || item.deleteMarked) && (
          <span className="absolute bottom-1.5 left-1.5 flex items-center gap-1 text-sm leading-none drop-shadow">
            {item.favorite && <span className="text-amber-400">★</span>}
            {item.deleteMarked && <span className="text-red-400">🗑</span>}
          </span>
        )}
        {item.status !== "ready" && (
          <span
            className={`absolute top-1.5 left-1.5 text-[11px] px-1.5 py-0.5 rounded font-medium ${
              item.status === "error"
                ? "bg-red-600/85 text-white"
                : "bg-amber-400/90 text-black"
            }`}
          >
            {STATUS_LABEL[item.status] ?? item.status}
          </span>
        )}
        {item.score > 0 && (
          <span className="absolute top-1.5 right-1.5 text-[11px] bg-emerald-600/85 text-white px-1.5 py-0.5 rounded">
            {item.score.toFixed(1)}
          </span>
        )}
      </div>
      <div className="p-2.5">
        <p className="text-sm font-medium leading-snug line-clamp-2">{item.title}</p>
        {item.description && (
          <p className="mt-1 text-[11px] text-neutral-400 leading-snug line-clamp-2">
            {item.description}
          </p>
        )}
        <div className="mt-1.5 flex flex-wrap gap-1">
          {topTags.map((t) => (
            <span
              key={t.tag}
              className={`text-[11px] px-1.5 py-0.5 rounded ${
                matched && t.tag === matched.tag
                  ? "bg-emerald-600/30 text-emerald-300 ring-1 ring-emerald-600/50"
                  : t.category === "user"
                    ? "bg-pink-600/20 text-pink-300 ring-1 ring-pink-600/40"
                    : "bg-neutral-800 text-neutral-300"
              }`}
            >
              {t.tag}
              <span className="text-neutral-500"> {Math.round(t.confidence * 100)}%</span>
            </span>
          ))}
          {item.tags.length > 4 && (
            <span className="text-[11px] text-neutral-500 px-1">+{item.tags.length - 4}</span>
          )}
        </div>
      </div>
    </Link>
  );
}

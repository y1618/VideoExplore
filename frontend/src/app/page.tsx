"use client";

import { useCallback, useEffect, useState } from "react";
import VideoCard from "@/components/VideoCard";
import { API_BASE, fetchJSON } from "@/lib/api";
import type { SearchResponse, TagWithCount } from "@/lib/types";

const PAGE_SIZE = 24;

export default function Home() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [tags, setTags] = useState<TagWithCount[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState<string | null>(null);

  const load = useCallback(async (q: string, p: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchJSON<SearchResponse>(
        `/api/search?q=${encodeURIComponent(q)}&page=${p}&page_size=${PAGE_SIZE}`
      );
      setData(res);
    } catch {
      setError(`API に接続できません (${API_BASE})。docker compose up 状態を確認してください。`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(query, page);
  }, [query, page, load]);

  useEffect(() => {
    fetchJSON<TagWithCount[]>("/api/tags")
      .then((rows) => setTags(rows.filter((r) => r.count > 0)))
      .catch(() => {});
  }, [data]);

  // 解析中の動画があれば状態を定期更新
  const hasPending = data?.items.some(
    (i) => i.status !== "ready" && i.status !== "error"
  );
  useEffect(() => {
    if (!hasPending) return;
    const timer = setInterval(() => load(query, page), 6000);
    return () => clearInterval(timer);
  }, [hasPending, query, page, load]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setQuery(input.trim());
  };

  const searchTag = (tag: string) => {
    setInput(tag);
    setPage(1);
    setQuery(tag);
  };

  const doScan = async () => {
    setScanning(true);
    setScanMsg(null);
    try {
      const res = await fetchJSON<{ added: number }>("/api/admin/scan", {
        method: "POST",
      });
      setScanMsg(
        res.added > 0 ? `${res.added} 件の新規動画を検出、解析を開始しました` : "新規動画はありません"
      );
      await load(query, page);
    } catch {
      setScanMsg("スキャンに失敗しました(API ログを確認)");
    } finally {
      setScanning(false);
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.pageSize)) : 1;
  const pendingCount = data?.items.filter(
    (i) => i.status !== "ready" && i.status !== "error"
  ).length ?? 0;

  return (
    <main className="max-w-6xl mx-auto px-4 pb-16">
      <header className="sticky top-0 z-10 -mx-4 px-4 pt-5 pb-3 bg-neutral-950/90 backdrop-blur">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-xl font-bold tracking-tight mr-2">
            Video<span className="text-emerald-400">Explore</span>
          </h1>
          <form onSubmit={submit} className="flex-1 min-w-[240px] flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="検索ワード(例: 影、夜、車、森…)"
              className="flex-1 bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm
                         focus:outline-none focus:ring-2 focus:ring-emerald-500/60 placeholder:text-neutral-500"
            />
            <button
              type="submit"
              className="bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition"
            >
              検索
            </button>
          </form>
          <button
            onClick={doScan}
            disabled={scanning}
            className="border border-neutral-700 hover:border-neutral-500 text-sm px-3 py-2 rounded-lg transition
                       disabled:opacity-50 whitespace-nowrap"
          >
            {scanning ? "スキャン中…" : "スキャン"}
          </button>
        </div>

        {tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {tags.map((t) => (
              <button
                key={t.tag}
                onClick={() => searchTag(t.tag)}
                title={t.category ?? ""}
                className={`text-xs px-2 py-1 rounded-full border transition ${
                  query === t.tag
                    ? "bg-emerald-600 border-emerald-500 text-white"
                    : "bg-neutral-900 border-neutral-800 text-neutral-300 hover:border-emerald-600/60"
                }`}
              >
                {t.tag} <span className="text-neutral-500">{t.count}</span>
              </button>
            ))}
          </div>
        )}
      </header>

      {scanMsg && (
        <p className="mt-2 text-xs text-emerald-400">{scanMsg}</p>
      )}
      {error && (
        <div className="mt-6 rounded-lg border border-red-800 bg-red-950/40 text-red-300 text-sm p-4">
          {error}
        </div>
      )}

      {data && !error && (
        <>
          <div className="mt-4 flex items-baseline justify-between flex-wrap gap-2">
            <p className="text-sm text-neutral-400">
              {data.query ? (
                <>
                  「<span className="text-neutral-100 font-medium">{data.query}</span>」の検索結果:{" "}
                  <span className="text-neutral-100 font-medium">{data.total}</span> 件
                </>
              ) : (
                <>全動画 <span className="text-neutral-100 font-medium">{data.total}</span> 件(新着順)</>
              )}
              {pendingCount > 0 && (
                <span className="ml-2 text-amber-400 text-xs">
                  {pendingCount} 件 解析中…(自動更新)
                </span>
              )}
            </p>
            {data.matchedTags.length > 0 && (
              <p className="text-xs text-neutral-500">
                タグ候補:
                {data.matchedTags.map((t) => (
                  <button
                    key={t.tag}
                    onClick={() => searchTag(t.tag)}
                    className="ml-1.5 text-emerald-400 hover:underline"
                  >
                    {t.tag}({t.count})
                  </button>
                ))}
              </p>
            )}
          </div>

          {data.items.length === 0 ? (
            <div className="mt-10 text-center text-neutral-400">
              {data.query ? (
                <p>
                  「{data.query}」に一致する動画はありませんでした。
                  <br />
                  <span className="text-xs">
                    タグ解析が完了していない可能性があります。しばらく待ってから再検索してください。
                  </span>
                </p>
              ) : (
                <p>
                  動画がありません。
                  <br />
                  <span className="text-xs">
                    「スキャン」ボタンを実行するか、data/videos(SMB マウントポイント)に動画を配置してください。
                  </span>
                </p>
              )}
            </div>
          ) : (
            <div className="mt-4 grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
              {data.items.map((item) => (
                <VideoCard key={item.id} item={item} query={query} />
              ))}
            </div>
          )}

          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-3">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="text-sm border border-neutral-700 rounded-lg px-3 py-1.5 disabled:opacity-40 hover:border-neutral-500"
              >
                前へ
              </button>
              <span className="text-sm text-neutral-400">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="text-sm border border-neutral-700 rounded-lg px-3 py-1.5 disabled:opacity-40 hover:border-neutral-500"
              >
                次へ
              </button>
            </div>
          )}
        </>
      )}

      {loading && (
        <div className="fixed bottom-4 right-4 text-xs bg-neutral-800 px-3 py-1.5 rounded-full text-neutral-300">
          読み込み中…
        </div>
      )}
    </main>
  );
}

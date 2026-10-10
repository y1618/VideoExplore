"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
  const [favOnly, setFavOnly] = useState(false);
  const [delOnly, setDelOnly] = useState(false);
  const [sort, setSort] = useState<"new" | "random" | "old">("new");
  const [seed, setSeed] = useState(0);
  const [initialized, setInitialized] = useState(false);
  const [lastPlayed, setLastPlayed] = useState<number | null>(null);
  const restoreScrollRef = useRef(false);
  const anchorIdRef = useRef<number | null>(null);

  // URL パラメータがあれば検索状態を復元(/?q=...&page=...&favorite=...)
  useEffect(() => {
    if (initialized) return;
    setInitialized(true);
    const p = new URLSearchParams(window.location.search);
    const q = p.get("q") ?? "";
    if (q || p.get("favorite") || p.get("deleted") || p.get("sort") || p.get("page")) {
      restoreScrollRef.current = true;
    }
    try {
      const lp = sessionStorage.getItem("ve_last_played");
      if (lp) setLastPlayed(parseInt(lp, 10));
      const an = sessionStorage.getItem("ve_anchor_id");
      if (an) anchorIdRef.current = parseInt(an, 10);
    } catch {}
    if (q || p.get("favorite") || p.get("deleted") || p.get("sort") || p.get("page")) {
      setInput(q);
      setQuery(q);
      const pg = parseInt(p.get("page") ?? "1", 10);
      if (pg > 0) setPage(pg);
      if (p.get("favorite") === "true") setFavOnly(true);
      if (p.get("deleted") === "true") setDelOnly(true);
      if (p.get("sort") === "random") setSort("random");
      if (p.get("sort") === "old") setSort("old");
      const sd = parseInt(p.get("seed") ?? "0", 10);
      if (sd) setSeed(sd);
    }
  }, [initialized]);

  // 検索状態をセッションとURLに保存(動画ページの「検索に戻る」・ブラウザ戻る用)
  useEffect(() => {
    if (!initialized) return;
    const p = new URLSearchParams();
    if (query) p.set("q", query);
    if (page > 1) p.set("page", String(page));
    if (favOnly) p.set("favorite", "true");
    if (delOnly) p.set("deleted", "true");
    if (sort !== "new") {
      p.set("sort", sort);
      p.set("seed", String(seed));
    }
    const qs = p.toString();
    try {
      sessionStorage.setItem("ve_search", qs);
    } catch {}
    window.history.replaceState(null, "", qs ? `/?${qs}` : "/");
  }, [initialized, query, page, favOnly, delOnly, sort, seed]);

  // スクロール位置を保存(動画を再生して戻った時に復元する)
  useEffect(() => {
    let last = 0;
    const onScroll = () => {
      const now = Date.now();
      if (now - last < 200) return;
      last = now;
      try {
        sessionStorage.setItem("ve_scroll_pos", String(window.scrollY));
      } catch {}
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // 「検索に戻る」で戻ってきた際に、再生していたカード位置へ復元
  useEffect(() => {
    if (!data || !restoreScrollRef.current) return;
    restoreScrollRef.current = false;
    requestAnimationFrame(() => {
      let scrolled = false;
      if (anchorIdRef.current) {
        const el = document.querySelector(`[data-vid="${anchorIdRef.current}"]`);
        if (el) {
          el.scrollIntoView({ block: "center" });
          scrolled = true;
        }
      }
      if (!scrolled) {
        try {
          const saved = parseInt(sessionStorage.getItem("ve_scroll_pos") ?? "0", 10);
          if (saved > 0) window.scrollTo(0, saved);
        } catch {}
      }
    });
  }, [data]);

  const load = useCallback(
    async (
      q: string,
      p: number,
      fav: boolean,
      del: boolean,
      so: string,
      sd: number,
      useCache: boolean = false
    ) => {
      setLoading(true);
      setError(null);
      const cacheKey = JSON.stringify([q, p, fav, del, so, sd, PAGE_SIZE]);
      // 復元時(戻ってきた直後)はキャッシュを優先し、並び替えによる変化を防ぐ
      if (useCache) {
        try {
          const raw = sessionStorage.getItem("ve_list_cache");
          if (raw) {
            const { key, res } = JSON.parse(raw) as { key: string; res: SearchResponse };
            if (key === cacheKey && Array.isArray(res?.items)) {
              setData(res);
              setLoading(false);
              return;
            }
          }
        } catch {}
      }
      try {
        const params = new URLSearchParams({
          q,
          page: String(p),
          page_size: String(PAGE_SIZE),
        });
        if (fav) params.set("favorite", "true");
        if (del) params.set("deleted", "true");
        if (so === "random") {
          params.set("sort", "random");
          params.set("seed", String(sd));
        } else if (so === "old") {
          params.set("sort", "old");
        }
        const res = await fetchJSON<SearchResponse>(`/api/search?${params}`);
        setData(res);
        try {
          sessionStorage.setItem("ve_list_cache", JSON.stringify({ key: cacheKey, res }));
        } catch {}
      } catch {
        setError(`API に接続できません (${API_BASE})。docker compose up 状態を確認してください。`);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (!initialized) return;
    load(query, page, favOnly, delOnly, sort, seed, restoreScrollRef.current);
  }, [initialized, query, page, favOnly, delOnly, sort, seed, load]);

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
    const timer = setInterval(
      () => load(query, page, favOnly, delOnly, sort, seed, false),
      6000
    );
    return () => clearInterval(timer);
  }, [hasPending, query, page, favOnly, delOnly, sort, seed, load]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setQuery(input.trim());
  };

  const clearSearch = () => {
    setInput("");
    setQuery("");
    setPage(1);
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
      await load(query, page, favOnly, delOnly, sort, seed);
    } catch {
      setScanMsg("スキャンに失敗しました(API ログを確認)");
    } finally {
      setScanning(false);
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.pageSize)) : 1;
  // ページ番号リスト(現在ページ前後 + 先頭/末尾、間は "…" 省略)
  const pageNumbers: (number | "ellipsis")[] = [];
  {
    const win = 2;
    const set = new Set<number>([1, totalPages]);
    for (let n = page - win; n <= page + win; n++) {
      if (n >= 1 && n <= totalPages) set.add(n);
    }
    let prev = 0;
    for (const n of [...set].sort((a, b) => a - b)) {
      if (prev && n - prev > 1) pageNumbers.push("ellipsis");
      pageNumbers.push(n);
      prev = n;
    }
  }
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
            <div className="relative flex-1">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="検索ワード(例: 影、夜、車、森…)"
                className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 pr-8 text-sm
                           focus:outline-none focus:ring-2 focus:ring-emerald-500/60 placeholder:text-neutral-500"
              />
              {input && (
                <button
                  type="button"
                  onClick={clearSearch}
                  aria-label="検索をクリア"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-500
                             hover:text-white text-sm leading-none transition"
                >
                  ✕
                </button>
              )}
            </div>
            <button
              type="submit"
              className="bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition"
            >
              検索
            </button>
          </form>
          <button
            onClick={() => {
              setFavOnly((v) => !v);
              setPage(1);
            }}
            className={`text-sm px-3 py-2 rounded-lg border transition whitespace-nowrap ${
              favOnly
                ? "bg-amber-500 border-amber-400 text-black hover:bg-amber-400"
                : "border-neutral-700 hover:border-neutral-500"
            }`}
          >
            ★ お気に入り
          </button>
          <button
            onClick={() => {
              setDelOnly((v) => !v);
              setPage(1);
            }}
            className={`text-sm px-3 py-2 rounded-lg border transition whitespace-nowrap ${
              delOnly
                ? "bg-red-700 border-red-500 text-white hover:bg-red-600"
                : "border-neutral-700 hover:border-neutral-500"
            }`}
          >
            🗑 削除マーク
          </button>
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
                <>全動画 <span className="text-neutral-100 font-medium">{data.total}</span> 件</>
              )}
              {pendingCount > 0 && (
                <span className="ml-2 text-amber-400 text-xs">
                  {pendingCount} 件 解析中…(自動更新)
                </span>
              )}
            </p>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => {
                  setSort("new");
                  setPage(1);
                }}
                className={`text-xs px-2.5 py-1 rounded-full border transition ${
                  sort === "new"
                    ? "bg-emerald-600 border-emerald-500 text-white"
                    : "bg-neutral-900 border-neutral-800 text-neutral-300 hover:border-neutral-500"
                }`}
              >
                新着順
              </button>
              <button
                onClick={() => {
                  setSort("old");
                  setPage(1);
                }}
                className={`text-xs px-2.5 py-1 rounded-full border transition ${
                  sort === "old"
                    ? "bg-emerald-600 border-emerald-500 text-white"
                    : "bg-neutral-900 border-neutral-800 text-neutral-300 hover:border-neutral-500"
                }`}
              >
                古い順
              </button>
              <button
                onClick={() => {
                  setSort("random");
                  setSeed(Date.now());
                  setPage(1);
                }}
                className={`text-xs px-2.5 py-1 rounded-full border transition ${
                  sort === "random"
                    ? "bg-emerald-600 border-emerald-500 text-white"
                    : "bg-neutral-900 border-neutral-800 text-neutral-300 hover:border-neutral-500"
                }`}
              >
                ランダム
              </button>
              {sort === "random" && (
                <button
                  onClick={() => setSeed(Date.now())}
                  title="並べ替え"
                  className="text-xs px-2 py-1 rounded-full border border-neutral-800 bg-neutral-900
                             text-neutral-300 hover:border-neutral-500 transition"
                >
                  🎲
                </button>
              )}
            </div>
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
              {delOnly ? (
                <p>
                  削除マーク付きの動画はありません。
                  <br />
                  <span className="text-xs">動画を開いて 🗑 ボタンで削除マークを付けられます。</span>
                </p>
              ) : favOnly ? (
                <p>
                  お気に入りに登録された動画はありません。
                  <br />
                  <span className="text-xs">動画を開いて ♡ ボタンでお気に入りに登録できます。</span>
                </p>
              ) : data.query ? (
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
                <VideoCard
                  key={item.id}
                  item={item}
                  query={query}
                  highlight={lastPlayed === item.id}
                />
              ))}
            </div>
          )}

          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-1 flex-wrap">
              <button
                onClick={() => setPage(1)}
                disabled={page <= 1}
                aria-label="最初のページ"
                title="最初のページ"
                className="text-sm border border-neutral-700 rounded-lg px-2.5 py-1.5 disabled:opacity-40 hover:border-neutral-500"
              >
                «
              </button>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="text-sm border border-neutral-700 rounded-lg px-3 py-1.5 disabled:opacity-40 hover:border-neutral-500"
              >
                前へ
              </button>
              {pageNumbers.map((n, i) =>
                n === "ellipsis" ? (
                  <span key={`e${i}`} className="text-sm text-neutral-500 px-1">
                    …
                  </span>
                ) : (
                  <button
                    key={n}
                    onClick={() => setPage(n)}
                    aria-current={n === page ? "page" : undefined}
                    className={`text-sm min-w-9 rounded-lg px-2 py-1.5 border transition ${
                      n === page
                        ? "bg-emerald-600 border-emerald-500 text-white font-medium"
                        : "bg-neutral-900 border-neutral-800 text-neutral-300 hover:border-neutral-500"
                    }`}
                  >
                    {n}
                  </button>
                )
              )}
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="text-sm border border-neutral-700 rounded-lg px-3 py-1.5 disabled:opacity-40 hover:border-neutral-500"
              >
                次へ
              </button>
              <button
                onClick={() => setPage(totalPages)}
                disabled={page >= totalPages}
                aria-label="最後のページ"
                title="最後のページ"
                className="text-sm border border-neutral-700 rounded-lg px-2.5 py-1.5 disabled:opacity-40 hover:border-neutral-500"
              >
                »
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

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchHashtagSuggestions, fetchHashtags, fetchJSON } from "@/lib/api";
import type { CommentItem } from "@/lib/types";

interface Suggestion {
  tag: string;
  count: number;
}

function renderText(text: string) {
  const parts = text.split(/([#＃][^\s#＃]+)/g);
  return parts.map((p, i) =>
    /^[#＃]/.test(p) ? (
      <span key={i} className="text-pink-400">
        {p}
      </span>
    ) : (
      <span key={i}>{p}</span>
    )
  );
}

export default function Comments({
  videoId,
  onChanged,
}: {
  videoId: number;
  onChanged: () => void;
}) {
  const [comments, setComments] = useState<CommentItem[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sugs, setSugs] = useState<Suggestion[]>([]);
  const [showSugs, setShowSugs] = useState(false);
  const [active, setActive] = useState(0);
  const [allTags, setAllTags] = useState<Suggestion[]>([]);
  const [showAll, setShowAll] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    fetchJSON<CommentItem[]>(`/api/videos/${videoId}/comments`)
      .then(setComments)
      .catch(() => {});
  }, [videoId]);

  useEffect(() => {
    load();
  }, [load]);

  // キャレット直前の #断片 を取り出す(空白/# 含むなら候補を出さない)
  const getFragment = () => {
    const el = inputRef.current;
    if (!el) return null;
    const pos = el.selectionStart ?? input.length;
    const before = input.slice(0, pos);
    const hash = before.lastIndexOf("#");
    if (hash === -1) return null;
    const frag = before.slice(hash + 1);
    if (frag === "" || /[\s#＃]/.test(frag)) return frag === "" ? { hash, frag, pos } : null;
    return { hash, frag, pos };
  };

  // 入力変更時に候補を取得
  useEffect(() => {
    const f = getFragment();
    if (!f) {
      setShowSugs(false);
      setSugs([]);
      return;
    }
    let alive = true;
    fetchHashtagSuggestions(f.frag)
      .then((rows) => {
        if (!alive) return;
        setSugs(rows);
        setActive(0);
        setShowSugs(true);
      })
      .catch(() => {
        if (alive) setShowSugs(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input]);

  // テキストボックスクリック(フォーカス)で全ハッシュタグ一覧を表示
  const onFocus = () => {
    if (!getFragment()) {
      fetchHashtags()
        .then((rows) => setAllTags(rows))
        .catch(() => {});
      setShowAll(true);
    }
  };

  const appendTag = (tag: string) => {
    const base = input.replace(/\s+$/, "");
    setInput(`${base ? base + " " : ""}#${tag} `);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const accept = (tag: string) => {
    const f = getFragment();
    if (!f) return;
    const next = input.slice(0, f.hash) + "#" + tag + " " + input.slice(f.pos);
    setInput(next);
    setShowSugs(false);
    setShowAll(false);
    setSugs([]);
    const caret = f.hash + tag.length + 2;
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(caret, caret);
      }
    });
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      await fetchJSON(`/api/videos/${videoId}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      setInput("");
      setShowSugs(false);
      load();
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const remove = async (cid: number) => {
    setBusy(true);
    try {
      await fetchJSON(`/api/videos/${videoId}/comments/${cid}`, { method: "DELETE" });
      load();
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showSugs || sugs.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % sugs.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a - 1 + sugs.length) % sugs.length);
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      accept(sugs[active].tag);
    } else if (e.key === "Escape") {
      setShowSugs(false);
      setShowAll(false);
    }
  };

  return (
    <div className="mt-6">
      <h2 className="text-sm font-medium text-neutral-400">コメント</h2>
      <form onSubmit={submit} className="mt-2">
        <div className="relative flex gap-2">
          <div className="relative flex-1">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              onFocus={onFocus}
              onBlur={() => setShowAll(false)}
              placeholder="メモを入力(#ハッシュタグ も検索対象になります)"
              className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm
                         focus:outline-none focus:ring-2 focus:ring-emerald-500/60 placeholder:text-neutral-500"
            />
            {showSugs && sugs.length > 0 ? (
              <ul className="absolute left-0 right-0 top-full mt-1 z-20 bg-neutral-900 ring-1 ring-neutral-700
                             rounded-lg overflow-hidden shadow-lg">
                {sugs.map((s, i) => (
                  <li key={s.tag}>
                    <button
                      type="button"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        accept(s.tag);
                      }}
                      onMouseEnter={() => setActive(i)}
                      className={`w-full text-left px-3 py-1.5 text-sm flex justify-between transition ${
                        i === active ? "bg-emerald-600/30 text-emerald-200" : "text-neutral-300"
                      }`}
                    >
                      <span className="text-pink-400">#{s.tag}</span>
                      <span className="text-neutral-500 text-xs">{s.count} 件</span>
                    </button>
                  </li>
                ))}
                <li className="px-3 py-1 text-[11px] text-neutral-600 border-t border-neutral-800">
                  ↑↓ で選択、Enter/Tab で補完、Esc で閉じる
                </li>
              </ul>
            ) : showAll && allTags.length > 0 ? (
              <ul
                className="absolute left-0 right-0 top-full mt-1 z-20 bg-neutral-900 ring-1 ring-neutral-700
                           rounded-lg shadow-lg max-h-48 overflow-y-auto"
              >
                <li className="sticky top-0 px-3 py-1 text-[11px] text-neutral-500 bg-neutral-900 border-b border-neutral-800">
                  ハッシュタグをクリックして追加(スクロールで全件表示)
                </li>
                {allTags.map((t) => (
                  <li key={t.tag}>
                    <button
                      type="button"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        appendTag(t.tag);
                      }}
                      className="w-full text-left px-3 py-1.5 text-sm flex justify-between
                                 hover:bg-emerald-600/20 transition"
                    >
                      <span className="text-pink-400">#{t.tag}</span>
                      <span className="text-neutral-500 text-xs">{t.count} 件</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition"
          >
            投稿
          </button>
        </div>
      </form>

      {comments.length > 0 && (
        <ul className="mt-3 space-y-2">
          {comments.map((c) => (
            <li
              key={c.id}
              className="bg-neutral-900 ring-1 ring-neutral-800 rounded-lg px-3 py-2 text-sm leading-relaxed"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="whitespace-pre-wrap break-all">{renderText(c.text)}</p>
                <button
                  onClick={() => remove(c.id)}
                  disabled={busy}
                  aria-label="コメント削除"
                  className="shrink-0 text-neutral-500 hover:text-red-400 text-xs transition disabled:opacity-40"
                >
                  ✕
                </button>
              </div>
              <p className="mt-1 text-[11px] text-neutral-600">
                {c.createdAt ? new Date(c.createdAt).toLocaleString("ja-JP") : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

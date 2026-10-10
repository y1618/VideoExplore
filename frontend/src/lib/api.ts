export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${path}`);
  }
  return res.json() as Promise<T>;
}

export const thumbUrl = (id: number) => `${API_BASE}/api/videos/${id}/thumb`;
export const streamUrl = (id: number) => `${API_BASE}/api/videos/${id}/stream`;

export function setFavorite(id: number, favorite: boolean) {
  return fetchJSON<{ id: number; favorite: boolean }>(`/api/videos/${id}/favorite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ favorite }),
  });
}

export function setDeleteMark(id: number, marked: boolean) {
  return fetchJSON<{ id: number; deleteMarked: boolean }>(`/api/videos/${id}/delete-mark`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ marked }),
  });
}

export function countPlay(id: number) {
  return fetchJSON<{ id: number; playCount: number }>(`/api/videos/${id}/played`, {
    method: "POST",
  });
}

export function fetchHashtagSuggestions(q: string) {
  return fetchJSON<{ tag: string; count: number }[]>(
    `/api/hashtags?q=${encodeURIComponent(q)}&limit=8`
  );
}

export function fetchHashtags() {
  return fetchJSON<{ tag: string; count: number }[]>(`/api/hashtags?limit=200`);
}

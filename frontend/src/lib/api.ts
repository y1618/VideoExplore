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

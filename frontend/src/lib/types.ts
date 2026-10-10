export interface TagRef {
  tag: string;
  confidence: number;
  framesHit?: number;
  category?: string | null;
}

export interface VideoItem {
  id: number;
  title: string;
  path: string;
  smbPath?: string | null;
  status: string;
  error?: string | null;
  duration: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  codec: string | null;
  size: number | null;
  profile?: string;
  favorite?: boolean;
  deleteMarked?: boolean;
  playCount?: number;
  score: number;
  proxyReady?: boolean;
  tags: TagRef[];
  description?: string | null;
  descriptionEn?: string | null;
  sceneTags?: string[];
  updatedAt?: string | null;
}

export interface SearchResponse {
  total: number;
  page: number;
  pageSize: number;
  query: string;
  matchedTags: { tag: string; count: number }[];
  items: VideoItem[];
}

export interface ListResponse {
  total: number;
  page: number;
  pageSize: number;
  items: VideoItem[];
}

export interface TagWithCount {
  tag: string;
  category: string | null;
  count: number;
}

export interface StatsResponse {
  total: number;
  tagged: number;
  byStatus: Record<string, number>;
}

export interface CommentItem {
  id: number;
  text: string;
  hashtags: string[];
  createdAt?: string | null;
}

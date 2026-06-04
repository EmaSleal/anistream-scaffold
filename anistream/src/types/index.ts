// ── Core domain types ────────────────────────────────────────────

export type AudioFormat = "sub" | "dub" | "dub-sub";

export type ContentRating = "G" | "PG" | "PG-13" | "14+" | "17+" | "R";

export type Genre =
  | "Action"
  | "Adventure"
  | "Comedy"
  | "Drama"
  | "Fantasy"
  | "Horror"
  | "Isekai"
  | "Mecha"
  | "Mystery"
  | "Romance"
  | "Sci-Fi"
  | "Shonen"
  | "Shojo"
  | "Slice of Life"
  | "Sports"
  | "Supernatural"
  | "Thriller";

export interface Series {
  id: string;
  title: string;
  slug: string;
  description: string;
  thumbnailUrl: string;
  bannerUrl: string;
  logoUrl?: string;
  rating: ContentRating;
  genres: Genre[];
  audioFormats: AudioFormat[];
  seasonCount: number;
  episodeCount: number;
  year: number;
  isSimulcast: boolean;
  isFeatured: boolean;
  score?: number;
  malId?: number;
  animeflvSlug?: string;
  franchiseId?: string;
  seasonOrder?: number;
  franchiseRelation?: string;
  mediaType?: string;
  animeflvDisabled?: boolean;
  broadcastDay?: string;
  broadcastTime?: string;
  broadcastTimezone?: string;
  airedFrom?: string;
  kitsuStatus?: string;
  lastSimulcastCheck?: string;
}

export interface Episode {
  id: string;
  seriesId: string;
  seriesTitle: string;
  season: number;
  episode: number;
  title: string;
  description: string;
  thumbnailUrl: string;
  duration: number; // seconds
  audioFormats: AudioFormat[];
  rating: ContentRating;
  releasedAt: string; // ISO date
  isSeen: boolean;
  progressSeconds?: number;
  animeflvSlug?: string;
}

export interface WatchlistItem {
  seriesId: string;
  addedAt: string;
  lastWatchedEpisodeId?: string;
}

export interface User {
  id: string;
  username: string;
  avatarUrl?: string;
  plan: "free" | "fan" | "mega-fan" | "ultimate-fan";
  watchlist: WatchlistItem[];
}

// ── UI / component-level types ────────────────────────────────────

export interface NavItem {
  label: string;
  href: string;
}

export interface PlayerState {
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  volume: number;
  isMuted: boolean;
  playbackRate: number;
  isFullscreen: boolean;
  showControls: boolean;
}

export type SortOption = "popularity" | "newest" | "oldest" | "title-asc" | "title-desc";

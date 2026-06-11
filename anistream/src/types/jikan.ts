export interface JikanAnime {
  mal_id: number;
  title: string;
  title_english: string | null;
  type: string | null;
  status: string | null;
  score: number | null;
  episodes: number | null;
  rating: string | null;
  images: { jpg: { image_url: string; small_image_url: string } };
}

export interface JikanPagination {
  current_page: number;
  last_visible_page: number;
  has_next_page: boolean;
}

export interface JikanSearchParams {
  q?: string;
  type?: "tv" | "movie" | "ova" | "special" | "ona" | "music" | "cm" | "pv" | "tv_special";
  status?: "airing" | "complete" | "upcoming";
  /** Allowed values: g, pg, pg13, r17, r — "rx" is rejected server-side and must NOT be sent */
  rating?: "g" | "pg" | "pg13" | "r17" | "r";
  min_score?: number;
  max_score?: number;
  order_by?: "score" | "popularity" | "title" | "start_date" | "members" | "rank";
  sort?: "asc" | "desc";
  genres?: string;
  genres_exclude?: string;
  start_date?: string;
  end_date?: string;
  letter?: string;
  page?: number;
  limit?: number;
}

export type JikanSearchResponse =
  | { data: JikanAnime[]; pagination: JikanPagination }
  | { error: string };

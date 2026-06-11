import type { Series, Episode } from "@/types";

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function mapRow(row: Record<string, unknown>): Series {
  return {
    id: row.id as string,
    title: row.title as string,
    slug: row.slug as string,
    description: (row.description as string) ?? "",
    thumbnailUrl: (row.thumbnailUrl as string) ?? "",
    bannerUrl: (row.bannerUrl as string) ?? "",
    rating: (row.rating as Series["rating"]) ?? "14+",
    genres: ((row.genres as string[]) ?? []) as Series["genres"],
    audioFormats: (row.audioFormats as Series["audioFormats"]) ?? ["sub"],
    seasonCount: (row.seasonCount as number) ?? 1,
    episodeCount: (row.episodeCount as number) ?? 0,
    year: (row.year as number) ?? 0,
    isSimulcast: (row.isSimulcast as boolean) ?? false,
    isFeatured: (row.isFeatured as boolean) ?? false,
    score: row.score as number | undefined,
    malId: row.malId as number | undefined,
    animeflvSlug: row.animeflvSlug as string | undefined,
    franchiseId: row.franchiseId as string | undefined,
    seasonOrder: row.seasonOrder as number | undefined,
    franchiseRelation: row.franchiseRelation as string | undefined,
    mediaType: row.mediaType as string | undefined,
    animeflvDisabled: (row.animeflvDisabled as boolean) ?? false,
    broadcastDay: row.broadcastDay as string | undefined,
    broadcastTime: row.broadcastTime as string | undefined,
    broadcastTimezone: row.broadcastTimezone as string | undefined,
    airedFrom: row.airedFrom as string | undefined,
    kitsuStatus: row.kitsuStatus as string | undefined,
    lastSimulcastCheck: row.lastSimulcastCheck as string | undefined,
  };
}

const BASE_URL = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";

async function apiFetch<T>(path: string, fallback: T): Promise<T> {
  try {
    const url = path.startsWith("http") ? path : `${BASE_URL}${path}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return fallback;
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

// ---------------------------------------------------------------------------
// Public API — same signatures as the old Supabase-backed lib
// ---------------------------------------------------------------------------

export interface SeriesListParams {
  limit?: number;
  sort?: string;
  genre?: string;
  year?: number;
  season?: string;
  consolidated?: boolean;
}

export async function getSeriesList(arg: number | SeriesListParams = 50): Promise<Series[]> {
  const params: SeriesListParams = typeof arg === "number" ? { limit: arg } : arg;
  const { limit = 50, sort = "score", genre, year, season, consolidated } = params;

  const qs = new URLSearchParams({ limit: String(limit), sort });
  if (genre) qs.set("genre", genre);
  if (year) qs.set("year", String(year));
  if (season) qs.set("season", season);
  if (consolidated) qs.set("consolidated", "true");

  const rows = await apiFetch<Record<string, unknown>[]>(
    `/api/series?${qs.toString()}`,
    [],
  );
  return rows.map(mapRow);
}




export async function getSimulcastSeries(limit = 50): Promise<Series[]> {
  const rows = await apiFetch<Record<string, unknown>[]>(
    `/api/series?simulcast=true&limit=${limit}`,
    [],
  );
  return rows.map(mapRow);
}

export async function getDiscoverSeries(): Promise<Series[]> {
  const rows = await apiFetch<Record<string, unknown>[]>("/api/series/discover", []);
  return rows.map(mapRow);
}

export async function getFeaturedSeries(): Promise<Series[]> {
  const rows = await apiFetch<Record<string, unknown>[]>(
    `/api/series?featured=true`,
    [],
  );
  return rows.map(mapRow);
}

export async function getSeriesById(id: string): Promise<Series | null> {
  try {
    const res = await fetch(`${BASE_URL}/api/series/${id}`, { cache: "no-store" });
    if (!res.ok) return null;
    const row = (await res.json()) as Record<string, unknown>;
    return mapRow(row);
  } catch {
    return null;
  }
}

export async function getSeriesByFranchiseId(franchiseId: string): Promise<Series[]> {
  const rows = await apiFetch<Record<string, unknown>[]>(
    `/api/series?franchise_id=${franchiseId}`,
    [],
  );
  return rows.map(mapRow);
}

export async function getSeriesStreamConfig(
  seriesId: string,
): Promise<{ animeflvDisabled: boolean; animeav1Slug: string | null }> {
  try {
    const res = await fetch(`${BASE_URL}/api/series/${seriesId}/stream-config`, { cache: "no-store" });
    if (!res.ok) return { animeflvDisabled: false, animeav1Slug: null };
    return (await res.json()) as { animeflvDisabled: boolean; animeav1Slug: string | null };
  } catch {
    return { animeflvDisabled: false, animeav1Slug: null };
  }
}

export interface SeasonEntry {
  label: string;
  seriesId: string;
  episodes: Episode[];
}

function mapEpisodeRow(row: Record<string, unknown>): Episode {
  const epNum = (row.episode as number) ?? 0;
  return {
    id: row.id as string,
    seriesId: row.seriesId as string,
    seriesTitle: (row.seriesTitle as string) ?? "",
    season: (row.season as number) ?? 1,
    episode: epNum,
    title: (row.title as string) ?? `Episode ${epNum}`,
    description: (row.description as string) ?? "",
    thumbnailUrl: (row.thumbnailUrl as string) ?? "",
    duration: (row.duration as number) ?? 0,
    audioFormats: (row.audioFormats as Episode["audioFormats"]) ?? ["sub"],
    rating: (row.rating as Episode["rating"]) ?? "14+",
    releasedAt: (row.releasedAt as string) ?? new Date().toISOString(),
    isSeen: (row.isSeen as boolean) ?? false,
    animeflvSlug: row.animeflvSlug as string | undefined,
  };
}

interface RawSeasonEntry {
  label: string;
  seriesId: string;
  episodes: Record<string, unknown>[];
}

export async function getSeriesSeasons(
  seriesId: string,
): Promise<{ seasons: SeasonEntry[]; initialSeasonIdx: number }> {
  try {
    const res = await fetch(`${BASE_URL}/api/series/${seriesId}/seasons`, { cache: "no-store" });
    if (!res.ok) return { seasons: [], initialSeasonIdx: 0 };
    const data = (await res.json()) as {
      seasons: RawSeasonEntry[];
      initialSeasonIdx: number;
    };
    const seasons: SeasonEntry[] = data.seasons.map((s) => ({
      label: s.label,
      seriesId: s.seriesId,
      episodes: s.episodes.map(mapEpisodeRow),
    }));
    return { seasons, initialSeasonIdx: data.initialSeasonIdx };
  } catch {
    return { seasons: [], initialSeasonIdx: 0 };
  }
}

/**
 * @deprecated Server-side `?consolidated=true` (`getSeriesList({ consolidated: true })`) is canonical.
 * Retained only for non-home callers; do not use on new code paths.
 */
const MEDIA_TYPE_RANK: Record<string, number> = { tv: 4, movie: 3, ova: 2, special: 1, ona: 1, music: 0 };

function mediaRank(s: Series): number {
  return MEDIA_TYPE_RANK[s.mediaType ?? "tv"] ?? 0;
}

export function consolidateFranchises(series: Series[]): Series[] {
  const seen = new Set<string>();
  const result: Series[] = [];

  for (const s of series) {
    if (!s.franchiseId) {
      result.push(s);
      continue;
    }
    if (seen.has(s.franchiseId)) continue;
    seen.add(s.franchiseId);

    const members = series.filter((m) => m.franchiseId === s.franchiseId);

    // Pick the member with the highest media type rank as the representative.
    const representative = members.reduce((best, m) =>
      mediaRank(m) > mediaRank(best) ? m : best
    );

    result.push(representative);
  }

  return result;
}

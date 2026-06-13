import type { Episode } from "@/types";

// ---------------------------------------------------------------------------
// Internal mapper — Flask returns camelCase episode objects that already
// match the Episode interface, but we normalise defaults here to be safe.
// ---------------------------------------------------------------------------

function mapRow(row: Record<string, unknown>): Episode {
  const epNum = (row.episode as number) ?? 0;
  return {
    id: row.id as string,
    seriesId: row.seriesId as string,
    seriesTitle: (row.seriesTitle as string) ?? (row.seriesId as string) ?? "",
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

const BASE_URL = process.env.APP_URL ?? "http://localhost:3000";

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

export async function getEpisodeByWatchId(
  id: string,
): Promise<{ episode: Episode; animeflvSlug: string } | null> {
  try {
    const res = await fetch(`${BASE_URL}/api/episodes/watch/${id}`, { cache: "no-store" });
    if (!res.ok) return null;
    const data = (await res.json()) as {
      episode: Record<string, unknown>;
      animeflvSlug: string;
    };
    return {
      episode: mapRow(data.episode),
      animeflvSlug: data.animeflvSlug,
    };
  } catch {
    return null;
  }
}

export async function getEpisodesBySeriesId(seriesId: string): Promise<Episode[]> {
  const rows = await apiFetch<Record<string, unknown>[]>(
    `/api/series/${seriesId}/episodes`,
    [],
  );
  return rows.map(mapRow);
}

export async function getEpisodeStreamUrl(
  id: string,
): Promise<{ url: string; source: "animeflv" | "animeav1" } | null> {
  try {
    const res = await fetch(`${BASE_URL}/api/episodes/watch/${id}/stream-url`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { url: string; source: "animeflv" | "animeav1" };
    return data;
  } catch {
    return null;
  }
}

export async function getAdjacentEpisodes(
  seriesId: string,
  episodeNumber: number,
): Promise<{ prev: Episode | null; next: Episode | null }> {
  try {
    const res = await fetch(
      `${BASE_URL}/api/episodes/${seriesId}/adjacent?episode_number=${episodeNumber}`,
      { cache: "no-store" },
    );
    if (!res.ok) return { prev: null, next: null };
    const data = (await res.json()) as {
      prev: Record<string, unknown> | null;
      next: Record<string, unknown> | null;
    };
    return {
      prev: data.prev ? mapRow(data.prev) : null,
      next: data.next ? mapRow(data.next) : null,
    };
  } catch {
    return { prev: null, next: null };
  }
}

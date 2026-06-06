import "server-only";
import { flaskFetch } from "@/lib/flask-client";

export interface RecentEpisode {
  id: string;
  seriesId: string;
  episodeNumber: number;
  title?: string;
  thumbnailUrl?: string;
  airedAt?: string;
  animeflvSlug?: string;
  seriesTitle: string;
  seriesThumbnailUrl?: string;
  isWatched?: boolean;
}

export async function getRecentSimulcastEpisodes(limit = 20, userId?: string): Promise<RecentEpisode[]> {
  try {
    const res = await flaskFetch(`/api/episodes/recent-simulcast?limit=${limit}`);
    if (!res.ok) return [];
    const episodes = (await res.json()) as RecentEpisode[];

    // If user is authenticated, fetch watch progress
    if (userId) {
      try {
        const progressRes = await fetch(`/api/progress/${userId}/watched-episodes`, {
          cache: "no-store",
        });
        if (progressRes.ok) {
          const watchedIds = (await progressRes.json()) as string[];
          const watchedSet = new Set(watchedIds);
          return episodes.map((ep) => ({
            ...ep,
            isWatched: watchedSet.has(ep.id),
          }));
        }
      } catch {
        // Fail-open: if progress fetch fails, just return episodes without isWatched
      }
    }

    return episodes;
  } catch (e) {
    console.error("[simulcast-episodes] getRecentSimulcastEpisodes failed:", e);
    return [];
  }
}

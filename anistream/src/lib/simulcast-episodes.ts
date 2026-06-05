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
}

export async function getRecentSimulcastEpisodes(limit = 20): Promise<RecentEpisode[]> {
  try {
    const res = await flaskFetch(`/api/episodes/recent-simulcast?limit=${limit}`);
    if (!res.ok) return [];
    return (await res.json()) as RecentEpisode[];
  } catch (e) {
    console.error("[simulcast-episodes] getRecentSimulcastEpisodes failed:", e);
    return [];
  }
}

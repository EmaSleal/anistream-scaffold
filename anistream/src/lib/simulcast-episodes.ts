import "server-only";
import { auth } from "@/auth";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskFetch, flaskAuthGet } from "@/lib/flask-client";

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
        const session = await auth();
        if (session?.user?.id) {
          const token = await mintInternalToken({
            sub: session.user.id,
            role: (session.user as { role?: string })?.role || "USER",
          });
          const progressRes = await flaskAuthGet(`/api/progress/watched-episodes`, token);
          if (progressRes.ok) {
            const rows = (await progressRes.json()) as { episode_id: string; progress_sec: number; duration_sec: number }[];
            const watchedSet = new Set(
              rows
                .filter((r) => r.duration_sec > 0 && r.duration_sec - r.progress_sec <= 120)
                .map((r) => r.episode_id),
            );
            return episodes.map((ep) => ({
              ...ep,
              isWatched: watchedSet.has(ep.id),
            }));
          }
        }
      } catch (e) {
        console.error("[simulcast-episodes] watched-episodes fetch failed:", e);
      }
    }

    return episodes;
  } catch (e) {
    console.error("[simulcast-episodes] getRecentSimulcastEpisodes failed:", e);
    return [];
  }
}

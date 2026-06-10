import "server-only";
import { auth } from "@/auth";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthGet } from "@/lib/flask-client";

interface EpisodeProgress {
  progressSec: number;
  durationSec: number;
}

export async function getEpisodeProgressMap(seriesId?: string): Promise<Map<string, EpisodeProgress>> {
  try {
    const session = await auth();
    if (!session?.user?.id) return new Map();

    const token = await mintInternalToken({
      sub: session.user.id,
      role: (session.user as { role?: string })?.role || "USER",
    });

    const path = seriesId
      ? `/api/progress/watched-episodes?series_id=${seriesId}`
      : `/api/progress/watched-episodes`;
    const res = await flaskAuthGet(path, token);
    if (!res.ok) return new Map();

    const rows = (await res.json()) as { episode_id: string; progress_sec: number; duration_sec: number }[];
    return new Map(rows.map((r) => [r.episode_id, { progressSec: r.progress_sec, durationSec: r.duration_sec }]));
  } catch (e) {
    console.error("[progress-server] getEpisodeProgressMap failed:", e);
    return new Map();
  }
}

export async function getLastWatchedInFranchise(memberIds: string[]): Promise<string | null> {
  if (!memberIds.length) return null;
  try {
    const session = await auth();
    if (!session?.user?.id) return null;

    const token = await mintInternalToken({
      sub: session.user.id,
      role: (session.user as { role?: string })?.role || "USER",
    });

    const params = new URLSearchParams({ series_ids: memberIds.join(",") });
    const res = await flaskAuthGet(`/api/progress/last-in-franchise?${params}`, token);
    if (!res.ok) return null;

    const data = (await res.json()) as { series_id: string | null };
    return data.series_id ?? null;
  } catch {
    return null;
  }
}

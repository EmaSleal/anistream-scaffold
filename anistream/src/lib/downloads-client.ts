export type JobPhase = "pending" | "downloading" | "done" | "failed" | "unknown";

export interface Source {
  source: "jkanime";
  available: boolean;
}

export async function fetchSources(seriesId: string, ep: number): Promise<Source[]> {
  const res = await fetch(
    `/api/admin/downloads/sources/${seriesId}?episode_number=${ep}`,
    { cache: "no-store" }
  );
  if (!res.ok) return [];
  const data = await res.json().catch(() => ({}));
  return data.sources ?? [];
}

export async function triggerDownload(
  seriesId: string,
  ep: number,
  source: string
): Promise<{ jobId: string; status: JobPhase }> {
  const res = await fetch("/api/admin/downloads/trigger", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ series_id: seriesId, episode_number: ep, source }),
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function pollJob(jobId: string): Promise<{ status: JobPhase; error?: string }> {
  const res = await fetch(`/api/admin/downloads/jobs/${jobId}`, { cache: "no-store" });
  if (!res.ok) return { status: "unknown" };
  return res.json().catch(() => ({ status: "unknown" }));
}

/** Episode numbers of a series stored on the NAS. Returns [] on any failure. */
export async function fetchDownloadedEpisodes(seriesId: string): Promise<number[]> {
  try {
    const res = await fetch(`/api/series/${seriesId}/downloaded-episodes`, {
      cache: "no-store",
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data?.episodeNumbers) ? data.episodeNumbers : [];
  } catch {
    return [];
  }
}

export type QueueStatus = "queued" | "downloading" | "done" | "failed";

export interface QueueItem {
  episodeNumber: number;
  status: QueueStatus;
  error: string | null;
}

/** Queue every missing episode of a series (ADR-019). Throws on failure. */
export async function enqueueSeries(
  seriesId: string
): Promise<{ queued: number; alreadyQueued: number }> {
  const res = await fetch(`/api/admin/downloads/series/${seriesId}/enqueue`, {
    method: "POST",
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error ?? `HTTP ${res.status}`);
  }
  const data = await res.json();
  return { queued: data.queued ?? 0, alreadyQueued: data.alreadyQueued ?? 0 };
}

export interface SeriesQueue {
  items: QueueItem[];
  /** Fresh NAS list; the server includes it only when some item is done. */
  downloadedEpisodes?: number[];
}

/** Queue rows of a series. Returns { items: [] } on any failure. */
export async function fetchSeriesQueue(seriesId: string): Promise<SeriesQueue> {
  try {
    const res = await fetch(`/api/admin/downloads/series/${seriesId}/queue`, {
      cache: "no-store",
    });
    if (!res.ok) return { items: [] };
    const data = await res.json();
    const result: SeriesQueue = { items: Array.isArray(data?.items) ? data.items : [] };
    if (Array.isArray(data?.downloadedEpisodes)) result.downloadedEpisodes = data.downloadedEpisodes;
    return result;
  } catch {
    return { items: [] };
  }
}

export interface QueueSummary {
  queued: number;
  downloadingEpisode: number | null;
  failed: number;
  active: boolean;
}

/**
 * Progress of the *current* run: a row per episode may exist from older runs
 * (done/failed history), so failed counts only episodes whose latest row failed.
 */
export function summarizeQueue(items: QueueItem[]): QueueSummary {
  const queued = items.filter((i) => i.status === "queued").length;
  const downloading = items.find((i) => i.status === "downloading");
  const latest = new Map<number, QueueStatus>();
  for (const i of items) latest.set(i.episodeNumber, i.status);
  let failed = 0;
  for (const s of latest.values()) if (s === "failed") failed++;
  return {
    queued,
    downloadingEpisode: downloading ? downloading.episodeNumber : null,
    failed,
    active: queued > 0 || !!downloading,
  };
}

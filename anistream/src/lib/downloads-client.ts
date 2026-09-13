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

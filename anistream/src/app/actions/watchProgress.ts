"use server";

/**
 * Watch-progress Server Actions — thin proxies to the Next.js route handlers.
 *
 * MOCK_EPISODES fallback has been REMOVED. All reads and writes are delegated
 * to Flask via the /api/progress route handlers.
 *
 * Server Actions have no `req` object; they forward session cookies to the
 * same-origin handlers which handle token minting (Auth mechanism A2).
 */

import { cookies } from "next/headers";
import type { Episode } from "@/types";

function getBaseUrl(): string {
  return process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
}

async function getCookieHeader(): Promise<string> {
  const cookieStore = await cookies();
  return cookieStore
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
}

export async function saveWatchProgress(
  episodeId: string,
  seriesId: string,
  progressSec: number,
  durationSec: number
): Promise<void> {
  if (progressSec <= 0) return;

  const cookieHeader = await getCookieHeader();
  await fetch(`${getBaseUrl()}/api/progress`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: cookieHeader,
    },
    body: JSON.stringify({
      episode_id: episodeId,
      series_id: seriesId,
      progress_sec: progressSec,
      duration_sec: durationSec,
    }),
    cache: "no-store",
  });
}

export async function getEpisodeProgress(episodeId: string): Promise<number> {
  const cookieHeader = await getCookieHeader();
  const res = await fetch(`${getBaseUrl()}/api/progress/${episodeId}`, {
    headers: { Cookie: cookieHeader },
    cache: "no-store",
  });

  if (!res.ok) return 0;

  const data = (await res.json()) as { progress_sec?: number };
  return data.progress_sec ?? 0;
}

export async function advanceToNextEpisode(
  currentEpisodeId: string,
  currentSeriesId: string,
  durationSec: number,
  nextEpisodeId: string,
  nextSeriesId: string
): Promise<void> {
  try {
    const cookieHeader = await getCookieHeader();
    await fetch(`${getBaseUrl()}/api/progress/advance`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: cookieHeader,
      },
      body: JSON.stringify({
        current_episode_id: currentEpisodeId,
        current_series_id: currentSeriesId,
        duration_sec: durationSec,
        next_episode_id: nextEpisodeId,
        next_series_id: nextSeriesId,
      }),
      cache: "no-store",
    });
  } catch {
    // Fire-and-forget: progress failure must never block navigation
  }
}

export async function getContinueWatching() {
  const cookieHeader = await getCookieHeader();
  const res = await fetch(`${getBaseUrl()}/api/progress/continue-watching`, {
    headers: { Cookie: cookieHeader },
    cache: "no-store",
  });

  if (!res.ok) return [];

  const data = (await res.json()) as { episode: Record<string, unknown>; progressSeconds: number }[];
  return (data.map((item) => ({ ...item.episode, progressSeconds: item.progressSeconds })) as (Episode & { progressSeconds: number })[])
    .filter((ep) => !(ep.duration > 0 && ep.duration - ep.progressSeconds <= 120));
}

/**
 * Fetch the most-recently-watched episodes for the authenticated user.
 *
 * Differences from getContinueWatching:
 *  - NO 120s near-completion filter — history is intentionally unfiltered.
 *  - Maps directly from the backend response without further filtering.
 */
export async function getWatchHistory(limit = 25): Promise<(Episode & { progressSeconds: number })[]> {
  const cookieHeader = await getCookieHeader();
  const res = await fetch(`${getBaseUrl()}/api/progress/history?limit=${limit}`, {
    headers: { Cookie: cookieHeader },
    cache: "no-store",
  });

  if (!res.ok) return [];

  const data = (await res.json()) as { episode: Record<string, unknown>; progressSeconds: number }[];
  return data.map((item) => ({ ...item.episode, progressSeconds: item.progressSeconds })) as (Episode & { progressSeconds: number })[];
}

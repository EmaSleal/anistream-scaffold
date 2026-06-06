"use server";

import { cookies } from "next/headers";

export interface SimulcastSeries {
  id: string;
  title: string;
  animeflvSlug: string | null;
  malId: number | null;
  isSimulcast: boolean;
  lastSimulcastCheck: string | null;
  score: number | null;
}

export interface SyncResult {
  added: number;
  updated: number;
  skipped: number;
}

function getAppUrl(): string {
  return process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
}

/**
 * Fetch all simulcast series from the admin route handler.
 * Called from the server component page during render.
 */
export async function getSimulcastSeries(): Promise<SimulcastSeries[]> {
  const cookieStore = await cookies();
  const appUrl = getAppUrl();

  const res = await fetch(`${appUrl}/api/admin/simulcast`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      Cookie: cookieStore.toString(),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(
      (data as { error?: string }).error ?? `Request failed with status ${res.status}`,
    );
  }

  return res.json() as Promise<SimulcastSeries[]>;
}

/**
 * Update the animeflv_slug for a simulcast series.
 * Pass null or empty string to clear the field.
 */
export async function updateSimulcastSlug(
  seriesId: string,
  slug: string | null,
): Promise<{ id: string; animeflvSlug: string | null }> {
  const cookieStore = await cookies();
  const appUrl = getAppUrl();

  const res = await fetch(`${appUrl}/api/admin/simulcast/${seriesId}/slug`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Cookie: cookieStore.toString(),
    },
    body: JSON.stringify({ slug }),
    cache: "no-store",
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(
      (data as { error?: string }).error ?? `Request failed with status ${res.status}`,
    );
  }

  return res.json() as Promise<{ id: string; animeflvSlug: string | null }>;
}

/**
 * Trigger a Jikan seasons/now sync to reconcile the DB with currently airing anime.
 * Returns counts of added, updated, and skipped series.
 */
export async function syncFromJikan(): Promise<SyncResult> {
  const cookieStore = await cookies();
  const appUrl = getAppUrl();

  const res = await fetch(`${appUrl}/api/admin/simulcast/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: cookieStore.toString(),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(
      (data as { error?: string }).error ?? `Request failed with status ${res.status}`,
    );
  }

  return res.json() as Promise<SyncResult>;
}

"use server";

/**
 * Watchlist Server Actions — thin proxies to the Next.js route handlers.
 *
 * Server Actions have no `req` object and cannot call getToken() directly.
 * Instead, they forward the session cookie to the same-origin route handlers
 * (GET/POST/DELETE /api/watchlist) which handle token minting and Flask proxying.
 *
 * IMPORTANT: cookies() from next/headers must be awaited in Next.js 15+.
 */

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import type { Series } from "@/types";

function getBaseUrl(): string {
  // In server-side context, we must use an absolute URL for fetch.
  // APP_URL or fall back to localhost for dev.
  return process.env.APP_URL ?? "http://localhost:3000";
}

async function getCookieHeader(): Promise<string> {
  const cookieStore = await cookies();
  return cookieStore
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
}

export async function addToWatchlist(seriesId: string): Promise<void> {
  const cookieHeader = await getCookieHeader();
  await fetch(`${getBaseUrl()}/api/watchlist`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: cookieHeader,
    },
    body: JSON.stringify({ series_id: seriesId }),
    cache: "no-store",
  });

  revalidatePath("/");
  revalidatePath("/my-lists");
}

export async function removeFromWatchlist(seriesId: string): Promise<void> {
  const cookieHeader = await getCookieHeader();
  await fetch(`${getBaseUrl()}/api/watchlist/${seriesId}`, {
    method: "DELETE",
    headers: {
      Cookie: cookieHeader,
    },
    cache: "no-store",
  });

  revalidatePath("/");
  revalidatePath("/my-lists");
}

/**
 * Toggle add/remove for a series. Used by HeroBanner.
 * Checks the current watchlist state and delegates to add or remove.
 */
export async function toggleWatchlist(seriesId: string): Promise<void> {
  const cookieHeader = await getCookieHeader();

  // Fetch the current list to determine toggle direction.
  const res = await fetch(`${getBaseUrl()}/api/watchlist`, {
    headers: { Cookie: cookieHeader },
    cache: "no-store",
  });

  if (!res.ok) {
    // Not authenticated or error — silently return.
    return;
  }

  const list = (await res.json()) as Series[];
  const isInList = list.some((s) => s.id === seriesId);

  if (isInList) {
    await removeFromWatchlist(seriesId);
  } else {
    await addToWatchlist(seriesId);
  }
}

/**
 * Return an array of series IDs in the user's watchlist.
 * Used by the home page and account page to show toggle state.
 * Derived from the full GET /api/watchlist response (no separate ids endpoint).
 */
export async function getWatchlistIds(): Promise<string[]> {
  const cookieHeader = await getCookieHeader();

  const res = await fetch(`${getBaseUrl()}/api/watchlist`, {
    headers: { Cookie: cookieHeader },
    cache: "no-store",
  });

  if (!res.ok) return [];

  const list = (await res.json()) as Series[];
  return list.map((s) => s.id);
}

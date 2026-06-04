"use server";

/**
 * Recommendations Server Action — thin proxy to the Next.js route handler.
 *
 * Forwards session cookies to /api/recommendations, which mints the internal
 * JWT and proxies to Flask. Returns an empty array on any error (fail-open).
 */

import { cookies } from "next/headers";
import type { Series } from "@/types";

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

export async function getRecommendations(): Promise<Series[]> {
  try {
    const cookieHeader = await getCookieHeader();
    const res = await fetch(`${getBaseUrl()}/api/recommendations`, {
      headers: { Cookie: cookieHeader },
      cache: "no-store",
    });

    if (!res.ok) return [];

    const data = (await res.json()) as Series[];
    return data;
  } catch {
    return [];
  }
}

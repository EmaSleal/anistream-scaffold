"use server";

import { cookies } from "next/headers";

export async function saveAnimeav1Source(
  seriesId: string,
  fallbackSlug: string
): Promise<void> {
  const cookieStore = await cookies();
  const appUrl = process.env.APP_URL ?? "http://localhost:3000";

  const res = await fetch(`${appUrl}/api/series/${seriesId}/stream-source`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Cookie: cookieStore.toString(),
    },
    body: JSON.stringify({ fallback_slug: fallbackSlug }),
    cache: "no-store",
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(
      (data as { error?: string }).error ?? `Request failed with status ${res.status}`
    );
  }
}


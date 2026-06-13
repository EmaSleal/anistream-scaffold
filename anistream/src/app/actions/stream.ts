"use server";

import { cookies } from "next/headers";

export async function saveAnimeav1Source(
  seriesId: string,
  animeav1Slug: string
): Promise<void> {
  const cookieStore = await cookies();
  const appUrl = process.env.APP_URL ?? "http://localhost:3000";

  const res = await fetch(`${appUrl}/api/series/${seriesId}/stream-source`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Cookie: cookieStore.toString(),
    },
    body: JSON.stringify({ animeav1_slug: animeav1Slug }),
    cache: "no-store",
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(
      (data as { error?: string }).error ?? `Request failed with status ${res.status}`
    );
  }
}


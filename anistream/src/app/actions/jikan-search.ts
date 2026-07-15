"use server";

import type { JWT } from "next-auth/jwt";
import { auth } from "@/auth";
import { redirect } from "next/navigation";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthGet } from "@/lib/flask-client";
import type { JikanAnime, JikanPagination, JikanSearchParams, JikanSearchResponse } from "@/types/jikan";

export async function searchJikan(
  params: JikanSearchParams
): Promise<JikanSearchResponse> {
  const session = await auth();
  if (!session || session.user.role !== "ADMIN") {
    redirect("/login");
  }

  // Build URLSearchParams from caller-supplied values.
  // Content guards (sfw, approved, genres_exclude, min_score default, rx rating)
  // are enforced on the Flask side — do not duplicate them here.
  const sp = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    sp.set(key, String(value));
  }

  const token: JWT = {
    sub: session.user?.email || "unknown",
    role: (session.user as { role?: string })?.role || "USER",
  };

  const internalToken = await mintInternalToken(token);

  try {
    const res = await flaskAuthGet(`/api/jikan/anime?${sp.toString()}`, internalToken);

    if (res.status === 429) {
      return { error: "Rate limit reached — Jikan is throttling requests. Wait a moment and try again." };
    }

    if (!res.ok) {
      return { error: `Jikan request failed (${res.status}).` };
    }

    const json = (await res.json()) as { data: JikanAnime[]; pagination: JikanPagination };
    return { data: json.data, pagination: json.pagination };
  } catch (err) {
    return { error: err instanceof Error ? err.message : "Network error — unable to reach Flask." };
  }
}

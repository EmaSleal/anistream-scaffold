"use server";

import { auth } from "@/auth";
import { redirect } from "next/navigation";
import type { JikanAnime, JikanPagination, JikanSearchParams, JikanSearchResponse } from "@/types/jikan";

export async function searchJikan(
  params: JikanSearchParams
): Promise<JikanSearchResponse> {
  const session = await auth();
  if (!session || session.user.role !== "ADMIN") {
    redirect("/login");
  }

  // Build URLSearchParams from caller-supplied values.
  // Strip any sfw/approved keys the caller might smuggle in (the type disallows
  // them, but strip defensively before the guard runs).
  const { sfw: _sfw, approved: _approved, ...safeParams } = params as JikanSearchParams & {
    sfw?: unknown;
    approved?: unknown;
  };
  void _sfw;
  void _approved;

  const sp = new URLSearchParams();

  for (const [key, value] of Object.entries(safeParams)) {
    if (value === undefined || value === null) continue;
    // Reject rx at the server level even though the TS type disallows it
    if (key === "rating" && String(value) === "rx") continue;
    sp.set(key, String(value));
  }

  // Default quality floor — skip unscored/obscure entries unless caller sets their own min.
  if (!sp.has("min_score")) sp.set("min_score", "5");

  // Content guard — executed LAST so these values can never be overridden by caller.
  sp.set("sfw", "true");
  sp.set("approved", "true");
  // Redundant but explicit: if somehow "rx" reached the params, delete it.
  if (sp.get("rating") === "rx") sp.delete("rating");
  // Hentai (MAL genre 12) — always excluded regardless of caller input.
  const existingExclude = sp.get("genres_exclude");
  const excludeIds = existingExclude
    ? [...new Set([...existingExclude.split(","), "12"])]
    : ["12"];
  sp.set("genres_exclude", excludeIds.join(","));

  try {
    const res = await fetch(`https://api.jikan.moe/v4/anime?${sp.toString()}`, {
      cache: "no-store",
    });

    if (res.status === 429) {
      return { error: "Rate limit reached, please wait a moment." };
    }

    if (!res.ok) {
      return { error: `Jikan request failed (${res.status}).` };
    }

    const json = (await res.json()) as { data: JikanAnime[]; pagination: JikanPagination };
    return { data: json.data, pagination: json.pagination };
  } catch {
    return { error: "Network error — unable to reach Jikan." };
  }
}

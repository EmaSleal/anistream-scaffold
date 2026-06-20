"use server";

import type { JWT } from "next-auth/jwt";
import { auth } from "@/auth";
import { flaskFetch } from "@/lib/flask-client";

export interface SeriesResult {
  id: string;
  mal_id: number;
  title: string;
  slug: string;
}

export interface AnimeFlvResult {
  title: string;
  slug: string;
  animeflv_url: string;
}

export async function searchSeries(query: string): Promise<SeriesResult[]> {
  if (!query || query.trim().length < 2) return [];
  const params = new URLSearchParams({ q: query.trim(), limit: "8" });
  const res = await flaskFetch("/api/series/search", params);
  if (!res.ok) return [];
  const raw = (await res.json()) as Array<{ id: string; malId: number; title: string; slug: string }>;
  return raw.map((r) => ({ id: r.id, mal_id: r.malId, title: r.title, slug: r.slug }));
}

export async function searchAnimeFlv(query: string): Promise<AnimeFlvResult[]> {
  if (!query || query.trim().length < 2) {
    return [];
  }

  const session = await auth();
  if (!session) {
    throw new Error("Unauthorized");
  }

  // Since this is a server action, we need to call Flask directly with the internal token
  const { mintInternalToken } = await import("@/lib/internal-token");
  const { flaskAuthGet } = await import("@/lib/flask-client");

  // Construct JWT-like object from Auth.js session
  // Note: session.user.role is set by the callbacks in auth.ts
  const token: JWT = {
    sub: session.user?.email || "unknown",
    role: (session.user as { role?: string })?.role || "USER",
  };

  const internalToken = await mintInternalToken(token);
  const params = new URLSearchParams({ q: query.trim(), limit: "10" });

  const flaskRes = await flaskAuthGet(
    `/api/series/search-animeflv?${params.toString()}`,
    internalToken,
  );

  if (!flaskRes.ok) {
    const errBody = await flaskRes.text();
    console.error("[searchAnimeFlv] Flask error:", flaskRes.status, errBody);
    throw new Error(`Flask search failed: ${flaskRes.status}`);
  }

  return (await flaskRes.json()) as AnimeFlvResult[];
}

interface IngestResult {
  series_id: string;
  series_title: string;
  episodes_ingested: number;
  kitsu_id: string | null;
  kitsu_episodes_matched: number;
}

export async function ingestSeries(
  slug: string | undefined,
  malId: number,
  fallbackSlug?: string
): Promise<IngestResult> {
  const session = await auth();
  if (session?.user?.role !== "ADMIN") {
    throw new Error("Unauthorized");
  }

  const flaskUrl = process.env.FLASK_URL ?? "http://localhost:5000";
  const res = await fetch(`${flaskUrl}/api/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ animeflv_slug: slug || undefined, mal_id: malId, fallback_slug: fallbackSlug || undefined }),
    cache: "no-store",
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error((data as { error?: string }).error ?? "Ingest failed");
  }

  return data as IngestResult;
}

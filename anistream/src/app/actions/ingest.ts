"use server";

import { auth } from "@/auth";
import { flaskFetch } from "@/lib/flask-client";

export interface SeriesResult {
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
  const raw = (await res.json()) as Array<{ malId: number; title: string; slug: string }>;
  return raw.map((r) => ({ mal_id: r.malId, title: r.title, slug: r.slug }));
}

export async function searchAnimeFlv(query: string): Promise<AnimeFlvResult[]> {
  if (!query || query.trim().length < 2) return [];

  const session = await auth();
  if (!session) {
    throw new Error("Unauthorized");
  }

  // Import here to avoid top-level server-side dependencies
  const { mintInternalToken } = await import("@/lib/internal-token");
  const { flaskAuthGet } = await import("@/lib/flask-client");

  const internalToken = await mintInternalToken(session);
  const params = new URLSearchParams({ q: query.trim(), limit: "10" });

  const res = await flaskAuthGet(`/api/series/search-animeflv?${params}`, internalToken);

  if (!res.ok) return [];
  return (await res.json()) as AnimeFlvResult[];
}

interface IngestResult {
  series_id: string;
  series_title: string;
  episodes_ingested: number;
  kitsu_id: string | null;
  kitsu_episodes_matched: number;
}

export async function ingestSeries(
  slug: string,
  malId: number,
  animeav1Slug?: string
): Promise<IngestResult> {
  const session = await auth();
  if (session?.user?.role !== "ADMIN") {
    throw new Error("Unauthorized");
  }

  const flaskUrl = process.env.FLASK_URL ?? "http://localhost:5000";
  const res = await fetch(`${flaskUrl}/api/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ animeflv_slug: slug, mal_id: malId, animeav1_slug: animeav1Slug || undefined }),
    cache: "no-store",
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error((data as { error?: string }).error ?? "Ingest failed");
  }

  return data as IngestResult;
}

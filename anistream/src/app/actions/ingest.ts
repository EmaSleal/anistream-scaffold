"use server";

import type { JWT } from "next-auth/jwt";
import { auth } from "@/auth";
import { flaskFetch } from "@/lib/flask-client";
import { mintInternalToken } from "@/lib/internal-token";

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

export interface FranchiseMember {
  mal_id: number;
  title: string;
  relation: string;
  season_order: number;
  already_in_catalog: boolean;
}

export interface IngestResult {
  series_id: string;
  series_title: string;
  episodes_ingested: number;
  principal_slug: string | null;
  kitsu_id: string | null;
  kitsu_episodes_matched: number;
  franchise_id: string;
  franchise_members: FranchiseMember[];
}

export interface IngestMemberInput {
  mal_id: number;
  franchise_id: string;
  season_order: number;
  relation: string;
  title?: string;
}

export interface IngestMemberResult {
  mal_id: number;
  status: string;
  episodes_ingested: number;
  principal_slug: string | null;
}

async function postFlaskAsAdmin<T>(
  path: string,
  payload: unknown,
  opts: { adminOrigin?: boolean } = {}
): Promise<T> {
  const session = await auth();
  if (session?.user?.role !== "ADMIN") {
    throw new Error("Unauthorized");
  }

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  let body = payload;
  if (opts.adminOrigin) {
    // ADR-016: only an admin-provided slug may bypass match validation. Flask
    // honors `slug_source: "admin"` only together with a verified admin token.
    const internalToken = await mintInternalToken({
      sub: session.user?.email || "unknown",
      role: "ADMIN",
    });
    headers.Authorization = `Bearer ${internalToken}`;
    body = { ...(payload as object), slug_source: "admin" };
  }

  const flaskUrl = process.env.FLASK_URL ?? "http://localhost:5000";
  const res = await fetch(`${flaskUrl}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    cache: "no-store",
  });

  // Flask answers JSON, but a gateway/gunicorn timeout answers HTML. Parse
  // defensively so the admin sees a readable message instead of a SyntaxError.
  let data: unknown = null;
  try {
    data = JSON.parse(await res.text());
  } catch {
    throw new Error(`Ingest failed (${res.status}): upstream timeout or non-JSON response`);
  }
  if (!res.ok) {
    const message = (data as { error?: string } | null)?.error ?? "unknown error";
    throw new Error(`Ingest failed (${res.status}): ${message}`);
  }

  return data as T;
}

function ingestPayload(malId: number, fallbackSlug?: string, animeav1Slug?: string) {
  return {
    mal_id: malId,
    fallback_slug: fallbackSlug || undefined,
    animeav1_slug: animeav1Slug || undefined,
  };
}

/**
 * Ingests only the requested series; related members come back in
 * `franchise_members`. Used by IngestTrigger: any slug it sends is a guess, so
 * it carries NO admin-origin marker or token and Flask validates it (ADR-016).
 */
export async function ingestSeries(
  malId: number,
  fallbackSlug?: string,
  animeav1Slug?: string
): Promise<IngestResult> {
  return postFlaskAsAdmin<IngestResult>("/api/ingest", ingestPayload(malId, fallbackSlug, animeav1Slug));
}

/**
 * Same as ingestSeries, for the admin Ingest/Browse forms: marks the slugs as
 * an admin decision (`slug_source: "admin"` + internal admin token), so Flask
 * skips the exact-match/validation rules for them.
 */
export async function ingestSeriesAsAdmin(
  malId: number,
  fallbackSlug?: string,
  animeav1Slug?: string
): Promise<IngestResult> {
  return postFlaskAsAdmin<IngestResult>(
    "/api/ingest",
    ingestPayload(malId, fallbackSlug, animeav1Slug),
    { adminOrigin: true }
  );
}

/** Ingests exactly one franchise member (ADR-015). */
export async function ingestFranchiseMember(
  input: IngestMemberInput
): Promise<IngestMemberResult> {
  return postFlaskAsAdmin<IngestMemberResult>("/api/ingest/member", input);
}

import { type NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthGet } from "@/lib/flask-client";
import type { JWT } from "next-auth/jwt";

/**
 * GET /api/admin/series/search-animeflv?q=...&limit=...
 *
 * Search AnimeFlv for anime slugs. Admin-only.
 * Proxies to Flask GET /api/series/search-animeflv with proper authentication.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const sessionToken = await getToken({
    req: request,
    secret: process.env.AUTH_SECRET,
  });

  if (!sessionToken) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const role = (sessionToken as JWT & { role?: string }).role;
  if (role !== "ADMIN") {
    return NextResponse.json({ error: "Forbidden: admin role required" }, { status: 403 });
  }

  const internalToken = await mintInternalToken(sessionToken);

  // Extract query params from Next.js request
  const { searchParams } = new URL(request.url);
  const q = searchParams.get("q");
  const limit = searchParams.get("limit") ?? "10";

  console.log("[search-animeflv] Received params:", { q, limit });

  // Proxy to Flask with the SAME params
  const flaskParams = new URLSearchParams();
  if (q) flaskParams.append("q", q);
  flaskParams.append("limit", limit);

  const flaskPath = `/api/series/search-animeflv?${flaskParams.toString()}`;
  console.log("[search-animeflv] Proxying to Flask:", flaskPath);

  const flaskRes = await flaskAuthGet(flaskPath, internalToken);
  console.log("[search-animeflv] Flask status:", flaskRes.status);

  const body = await flaskRes.json().catch(() => ({}));
  return NextResponse.json(body, { status: flaskRes.status });
}

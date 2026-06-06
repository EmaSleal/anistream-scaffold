import { type NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthGet } from "@/lib/flask-client";
import type { JWT } from "next-auth/jwt";

/**
 * GET /api/admin/series/search-animeflv?q=...
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
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("q") || "";
  const limit = searchParams.get("limit") || "10";

  const flaskParams = new URLSearchParams({ q: query, limit });
  const flaskRes = await flaskAuthGet(
    `/api/series/search-animeflv?${flaskParams}`,
    internalToken,
  );

  const body = await flaskRes.json().catch(() => ({}));
  return NextResponse.json(body, { status: flaskRes.status });
}

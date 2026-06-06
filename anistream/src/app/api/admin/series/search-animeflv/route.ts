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

  console.log(`[search-animeflv] Query: ${query}, Limit: ${limit}`);

  if (!query || query.trim().length < 2) {
    console.log("[search-animeflv] Query too short, returning empty");
    return NextResponse.json([], { status: 200 });
  }

  try {
    console.log(`[search-animeflv] Minting token...`);
    console.log(`[search-animeflv] Query: "${query}", Limit: "${limit}"`);

    const flaskParams = new URLSearchParams({ q: query, limit });
    const queryString = flaskParams.toString();
    console.log(`[search-animeflv] Query string: ${queryString}`);

    const flaskPath = `/api/series/search-animeflv?${queryString}`;
    console.log(`[search-animeflv] Calling Flask at: ${flaskPath}`);
    console.log(`[search-animeflv] Token: ${internalToken.substring(0, 20)}...`);

    const flaskRes = await flaskAuthGet(flaskPath, internalToken);

    console.log(`[search-animeflv] Flask response status: ${flaskRes.status}`);

    const body = await flaskRes.json().catch(() => {
      console.error("[search-animeflv] Failed to parse Flask response as JSON");
      return {};
    });
    console.log(`[search-animeflv] Flask response:`, body);

    return NextResponse.json(body, { status: flaskRes.status });
  } catch (err) {
    console.error("[search-animeflv] Exception:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 500 }
    );
  }
}

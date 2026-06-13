import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthGet, flaskAuthPost } from "@/lib/flask-client";

/**
 * GET /api/watchlist — proxy to Flask GET /api/watchlist.
 * Returns the authenticated user's watchlist as an array of Series objects.
 */
export async function GET() {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const internalToken = await mintInternalToken({
    sub: session.user.id,
    role: (session.user as { role?: string }).role ?? "USER",
  });
  const flaskRes = await flaskAuthGet("/api/watchlist", internalToken);
  const body = await flaskRes.json();
  return NextResponse.json(body, { status: flaskRes.status });
}

/**
 * POST /api/watchlist — proxy to Flask POST /api/watchlist.
 * Body: { series_id: string }
 */
export async function POST(request: NextRequest) {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json().catch(() => ({}));
  const internalToken = await mintInternalToken({
    sub: session.user.id,
    role: (session.user as { role?: string }).role ?? "USER",
  });
  const flaskRes = await flaskAuthPost("/api/watchlist", internalToken, body);
  const resBody = await flaskRes.json().catch(() => ({}));
  return NextResponse.json(resBody, { status: flaskRes.status });
}

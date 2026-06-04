import { type NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthPost } from "@/lib/flask-client";

/**
 * POST /api/progress — proxy to Flask POST /api/progress.
 * Body: { episode_id, series_id, progress_sec, duration_sec? }
 */
export async function POST(request: NextRequest) {
  const sessionToken = await getToken({
    req: request,
    secret: process.env.AUTH_SECRET,
  });

  if (!sessionToken) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json().catch(() => ({}));
  const internalToken = await mintInternalToken(sessionToken);
  const flaskRes = await flaskAuthPost("/api/progress", internalToken, body);
  const resBody = await flaskRes.json().catch(() => ({}));
  return NextResponse.json(resBody, { status: flaskRes.status });
}

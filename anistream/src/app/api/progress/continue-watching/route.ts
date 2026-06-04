import { type NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthGet } from "@/lib/flask-client";

/**
 * GET /api/progress/continue-watching — proxy to Flask GET /api/progress/continue-watching.
 * Returns an array of { episode, progressSeconds, seriesId } objects.
 */
export async function GET(request: NextRequest) {
  const sessionToken = await getToken({
    req: request,
    secret: process.env.AUTH_SECRET,
  });

  if (!sessionToken) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const internalToken = await mintInternalToken(sessionToken);
  const flaskRes = await flaskAuthGet("/api/progress/continue-watching", internalToken);
  const body = await flaskRes.json();
  return NextResponse.json(body, { status: flaskRes.status });
}

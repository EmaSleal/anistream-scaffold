import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthGet } from "@/lib/flask-client";

/**
 * GET /api/recommendations — proxy to Flask GET /api/series/recommendations.
 * Returns a Series[] array of personalized recommendations for the authenticated user.
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
  const flaskRes = await flaskAuthGet("/api/series/recommendations", internalToken);
  const body = await flaskRes.json();
  return NextResponse.json(body, { status: flaskRes.status });
}

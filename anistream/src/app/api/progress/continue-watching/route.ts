import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthGet } from "@/lib/flask-client";

/**
 * GET /api/progress/continue-watching — proxy to Flask GET /api/progress/continue-watching.
 * Returns an array of { episode, progressSeconds, seriesId } objects.
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
  const flaskRes = await flaskAuthGet("/api/progress/continue-watching", internalToken);
  const body = await flaskRes.json();
  return NextResponse.json(body, { status: flaskRes.status });
}

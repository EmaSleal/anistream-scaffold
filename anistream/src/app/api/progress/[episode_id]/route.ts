import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthGet } from "@/lib/flask-client";

/**
 * GET /api/progress/[episode_id] — proxy to Flask GET /api/progress/<episode_id>.
 * Returns { progress_sec: number }.
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ episode_id: string }> }
) {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { episode_id } = await params;
  const internalToken = await mintInternalToken({
    sub: session.user.id,
    role: (session.user as { role?: string }).role ?? "USER",
  });
  const flaskRes = await flaskAuthGet(`/api/progress/${episode_id}`, internalToken);
  const body = await flaskRes.json();
  return NextResponse.json(body, { status: flaskRes.status });
}

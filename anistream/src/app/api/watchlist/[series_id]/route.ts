import { type NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthDelete } from "@/lib/flask-client";

/**
 * DELETE /api/watchlist/[series_id] — proxy to Flask DELETE /api/watchlist/<series_id>.
 * Returns 204 on success, 401 if not authenticated.
 */
export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ series_id: string }> }
) {
  const sessionToken = await getToken({
    req: request,
    secret: process.env.AUTH_SECRET,
  });

  if (!sessionToken) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { series_id } = await params;
  const internalToken = await mintInternalToken(sessionToken);
  const flaskRes = await flaskAuthDelete(`/api/watchlist/${series_id}`, internalToken);

  if (flaskRes.status === 204) {
    return new NextResponse(null, { status: 204 });
  }

  const body = await flaskRes.json().catch(() => ({}));
  return NextResponse.json(body, { status: flaskRes.status });
}

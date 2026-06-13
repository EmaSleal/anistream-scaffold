import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthDelete } from "@/lib/flask-client";

/**
 * DELETE /api/watchlist/[series_id] — proxy to Flask DELETE /api/watchlist/<series_id>.
 * Returns 204 on success, 401 if not authenticated.
 */
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ series_id: string }> }
) {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { series_id } = await params;
  const internalToken = await mintInternalToken({
    sub: session.user.id,
    role: (session.user as { role?: string }).role ?? "USER",
  });
  const flaskRes = await flaskAuthDelete(`/api/watchlist/${series_id}`, internalToken);

  if (flaskRes.status === 204) {
    return new NextResponse(null, { status: 204 });
  }

  const body = await flaskRes.json().catch(() => ({}));
  return NextResponse.json(body, { status: flaskRes.status });
}

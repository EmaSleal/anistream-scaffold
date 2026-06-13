import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthPatch } from "@/lib/flask-client";

interface RouteContext {
  params: Promise<{ id: string }>;
}

/**
 * PATCH /api/series/[id]/stream-source
 *
 * Auth mechanism A2: decodes the Auth.js session, mints a short-lived
 * HS256 internal JWT, and forwards the request to Flask PATCH /api/series/<id>/stream-source.
 * Returns Flask's response verbatim. Returns 401 if no valid session is present.
 */
export async function PATCH(request: NextRequest, { params }: RouteContext): Promise<NextResponse> {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  const body = await request.json().catch(() => ({}));
  const internalToken = await mintInternalToken({
    sub: session.user.id,
    role: (session.user as { role?: string }).role ?? "USER",
  });
  const flaskRes = await flaskAuthPatch(
    `/api/series/${id}/stream-source`,
    internalToken,
    body,
  );
  const resBody = await flaskRes.json().catch(() => ({}));
  return NextResponse.json(resBody, { status: flaskRes.status });
}

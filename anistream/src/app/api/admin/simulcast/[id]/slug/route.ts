import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthPatch } from "@/lib/flask-client";

interface RouteContext {
  params: Promise<{ id: string }>;
}

/**
 * PATCH /api/admin/simulcast/[id]/slug
 *
 * Auth mechanism A2: decodes the Auth.js session, enforces ADMIN role,
 * mints a short-lived HS256 internal JWT, and proxies to Flask PATCH
 * /api/simulcast/<id>/slug.
 *
 * Request body: { slug: string | null }
 * Returns Flask's response verbatim ({id, animeflvSlug} on success).
 */
export async function PATCH(
  request: NextRequest,
  { params }: RouteContext,
): Promise<NextResponse> {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const role = (session.user as { role?: string }).role;
  if (role !== "ADMIN") {
    return NextResponse.json({ error: "Forbidden: admin role required" }, { status: 403 });
  }

  const { id } = await params;
  const body = await request.json().catch(() => ({}));
  const internalToken = await mintInternalToken({
    sub: session.user.id,
    role: role ?? "USER",
  });
  const flaskRes = await flaskAuthPatch(
    `/api/simulcast/${id}/slug`,
    internalToken,
    body,
  );
  const resBody = await flaskRes.json().catch(() => ({}));
  return NextResponse.json(resBody, { status: flaskRes.status });
}

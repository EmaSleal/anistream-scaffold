import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthPost } from "@/lib/flask-client";

/**
 * POST /api/admin/simulcast/sync
 *
 * Auth mechanism A2: decodes the Auth.js session, enforces ADMIN role,
 * mints a short-lived HS256 internal JWT, and proxies to Flask POST
 * /api/simulcast/sync-jikan.
 *
 * Returns {added, updated, skipped} on success, or {error} on failure.
 */
export async function POST(): Promise<NextResponse> {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const role = (session.user as { role?: string }).role;
  if (role !== "ADMIN") {
    return NextResponse.json({ error: "Forbidden: admin role required" }, { status: 403 });
  }

  const internalToken = await mintInternalToken({
    sub: session.user.id,
    role: role ?? "USER",
  });
  const flaskRes = await flaskAuthPost("/api/simulcast/sync-jikan", internalToken);
  const body = await flaskRes.json().catch(() => ({}));
  return NextResponse.json(body, { status: flaskRes.status });
}

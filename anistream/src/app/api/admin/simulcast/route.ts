import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthGet } from "@/lib/flask-client";

/**
 * GET /api/admin/simulcast
 *
 * Auth mechanism A2: decodes the Auth.js session, enforces ADMIN role,
 * mints a short-lived HS256 internal JWT, and proxies to Flask GET /api/simulcast/list.
 * Returns Flask's response verbatim (array of SimulcastSeries DTOs).
 */
export async function GET(): Promise<NextResponse> {
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
  const flaskRes = await flaskAuthGet("/api/simulcast/list", internalToken);
  const body = await flaskRes.json().catch(() => ({}));
  return NextResponse.json(body, { status: flaskRes.status });
}

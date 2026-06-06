import { type NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthGet } from "@/lib/flask-client";
import type { JWT } from "next-auth/jwt";

/**
 * GET /api/admin/simulcast
 *
 * Auth mechanism A2: decodes the Auth.js JWE session token, enforces ADMIN role,
 * mints a short-lived HS256 internal JWT, and proxies to Flask GET /api/simulcast/list.
 * Returns Flask's response verbatim (array of SimulcastSeries DTOs).
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const sessionToken = await getToken({
    req: request,
    secret: process.env.AUTH_SECRET,
  });

  if (!sessionToken) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const role = (sessionToken as JWT & { role?: string }).role;
  if (role !== "ADMIN") {
    return NextResponse.json({ error: "Forbidden: admin role required" }, { status: 403 });
  }

  const internalToken = await mintInternalToken(sessionToken);
  const flaskRes = await flaskAuthGet("/api/simulcast/list", internalToken);
  const body = await flaskRes.json().catch(() => ({}));
  return NextResponse.json(body, { status: flaskRes.status });
}

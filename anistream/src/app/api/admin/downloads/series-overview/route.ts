import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthGet } from "@/lib/flask-client";

export async function GET(req: NextRequest): Promise<NextResponse> {
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

  const flaskRes = await flaskAuthGet(
    `/api/admin/downloads/series-overview?${req.nextUrl.searchParams.toString()}`,
    internalToken
  );
  const body = await flaskRes.json().catch(() => ({}));
  return NextResponse.json(body, { status: flaskRes.status });
}

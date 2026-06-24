import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { mintInternalToken } from "@/lib/internal-token";
import { flaskAuthPost } from "@/lib/flask-client";

export async function POST(req: NextRequest): Promise<NextResponse> {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const role = (session.user as { role?: string }).role;
  if (role !== "ADMIN") {
    return NextResponse.json({ error: "Forbidden: admin role required" }, { status: 403 });
  }

  const body = await req.json().catch(() => ({}));
  const internalToken = await mintInternalToken({
    sub: session.user.id,
    role: role ?? "USER",
  });

  const flaskRes = await flaskAuthPost(
    "/api/admin/downloads/trigger",
    internalToken,
    body
  );
  const resBody = await flaskRes.json().catch(() => ({}));
  return NextResponse.json(resBody, { status: flaskRes.status });
}

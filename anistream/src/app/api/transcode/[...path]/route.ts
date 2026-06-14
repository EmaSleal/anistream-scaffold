import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

const FLASK_URL = process.env.FLASK_URL ?? "http://localhost:5000";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { path } = await params;
  const search = request.nextUrl.search;
  const upstreamUrl = `${FLASK_URL}/api/proxy/transcode/${path.join("/")}${search}`;

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, { cache: "no-store" });
  } catch {
    return NextResponse.json({ error: "Transcoding service unreachable" }, { status: 502 });
  }

  const headers = new Headers();
  const ct = upstream.headers.get("Content-Type");
  if (ct) headers.set("Content-Type", ct);
  headers.set("Accept-Ranges", "bytes");
  const cl = upstream.headers.get("Content-Length");
  if (cl) headers.set("Content-Length", cl);
  const cr = upstream.headers.get("Content-Range");
  if (cr) headers.set("Content-Range", cr);

  return new NextResponse(upstream.body, { status: upstream.status, headers });
}

import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

const FLASK_URL = process.env.FLASK_URL ?? "http://localhost:5000";

// Max time to wait for progressive transcode to have MIN_SEGMENTS ready.
const POLL_INTERVAL_MS = 5_000;
const POLL_MAX_ATTEMPTS = 24; // 24 × 5s = 120s

function forwardUpstream(upstream: Response): NextResponse {
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

  // Segment files (.ts) are served directly — no polling needed.
  const isPlaylist = path[path.length - 1] === "playlist.m3u8";

  if (!isPlaylist) {
    let upstream: Response;
    try {
      upstream = await fetch(upstreamUrl, { cache: "no-store" });
    } catch {
      return NextResponse.json({ error: "Transcoding service unreachable" }, { status: 502 });
    }
    return forwardUpstream(upstream);
  }

  // Playlist request: Flask returns 202 while transcoding, 200 when MIN_SEGMENTS ready.
  // Poll here so the browser client never sees a 202.
  for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt++) {
    let upstream: Response;
    try {
      upstream = await fetch(upstreamUrl, { cache: "no-store" });
    } catch {
      return NextResponse.json({ error: "Transcoding service unreachable" }, { status: 502 });
    }

    if (upstream.status !== 202) {
      return forwardUpstream(upstream);
    }

    if (attempt < POLL_MAX_ATTEMPTS - 1) {
      await new Promise<void>((r) => setTimeout(r, POLL_INTERVAL_MS));
    }
  }

  return NextResponse.json({ error: "Transcoding timed out" }, { status: 504 });
}

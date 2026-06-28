import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

const NAS_BASE_URL = process.env.NAS_BASE_URL ?? "";
const NAS_API_KEY = process.env.NAS_API_KEY ?? "";

export async function GET(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const rawUrl = request.nextUrl.searchParams.get("url");
  if (!rawUrl) {
    return NextResponse.json({ error: "Missing url" }, { status: 400 });
  }

  const targetUrl = decodeURIComponent(rawUrl);
  if (!NAS_BASE_URL || !targetUrl.startsWith(NAS_BASE_URL)) {
    return NextResponse.json({ error: "Invalid NAS URL" }, { status: 400 });
  }

  const range = request.headers.get("Range");

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, {
      headers: {
        "X-API-Key": NAS_API_KEY,
        ...(range ? { Range: range } : {}),
      },
    });
  } catch {
    return NextResponse.json({ error: "NAS unreachable" }, { status: 502 });
  }

  if (!upstream.ok && upstream.status !== 206) {
    return NextResponse.json({ error: "NAS error" }, { status: upstream.status });
  }

  const headers = new Headers();
  headers.set("Content-Type", upstream.headers.get("Content-Type") ?? "video/mp4");
  headers.set("Accept-Ranges", "bytes");

  const contentLength = upstream.headers.get("Content-Length");
  if (contentLength) headers.set("Content-Length", contentLength);

  const contentRange = upstream.headers.get("Content-Range");
  if (contentRange) headers.set("Content-Range", contentRange);

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers,
  });
}

import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

const ZILLA_HEADERS = {
  Referer: "https://animeav1.com/",
  Origin: "https://animeav1.com",
};

const ALLOWED_HOSTS = new Set(["player.zilla-networks.com"]);

const PROXY_PATH = "/api/stream/animeav1-proxy";

function rewriteM3u8(content: string, baseUrl: string): string {
  return content
    .split("\n")
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return line;

      if (trimmed.startsWith("#EXT-X-KEY")) {
        return trimmed.replace(/URI="([^"]+)"/, (_match, uri: string) => {
          const absolute = new URL(uri, baseUrl).toString();
          return `URI="${PROXY_PATH}?path=${encodeURIComponent(absolute)}"`;
        });
      }

      if (trimmed.startsWith("#")) return line;

      const absolute = new URL(trimmed, baseUrl).toString();
      return `${PROXY_PATH}?path=${encodeURIComponent(absolute)}`;
    })
    .join("\n");
}

export async function GET(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const rawPath = request.nextUrl.searchParams.get("path");
  if (!rawPath) {
    return NextResponse.json({ error: "Missing path" }, { status: 400 });
  }

  let targetUrl: URL;
  try {
    targetUrl = new URL(decodeURIComponent(rawPath));
  } catch {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }

  if (!ALLOWED_HOSTS.has(targetUrl.hostname)) {
    return NextResponse.json({ error: "Upstream host not allowed" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl.toString(), { headers: ZILLA_HEADERS });
  } catch {
    return NextResponse.json({ error: "Upstream unreachable" }, { status: 502 });
  }

  if (!upstream.ok) {
    return NextResponse.json({ error: "Upstream error" }, { status: 502 });
  }

  const contentType = upstream.headers.get("Content-Type") ?? "";
  const isM3u8 =
    contentType.includes("mpegurl") ||
    contentType.includes("x-mpegurl") ||
    targetUrl.pathname.endsWith(".m3u8");

  if (isM3u8) {
    const text = await upstream.text();
    const rewritten = rewriteM3u8(text, targetUrl.toString());
    return new NextResponse(rewritten, {
      headers: {
        "Content-Type": "application/vnd.apple.mpegurl",
        "Cache-Control": "no-cache",
      },
    });
  }

  return new NextResponse(upstream.body, {
    headers: {
      "Content-Type": contentType || "video/MP2T",
      "Cache-Control": "no-cache",
    },
  });
}

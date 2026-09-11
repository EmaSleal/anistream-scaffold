import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

const ZILLA_HEADERS = {
  Referer: "https://animeav1.com/",
  Origin: "https://animeav1.com",
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
};

const UPSTREAM_TIMEOUT_MS = 10_000;

const ALLOWED_HOSTS = new Set(["player.zilla-networks.com"]);

const PROXY_PATH = "/api/stream/animeav1-proxy";

const M3U8_CONTENT_TYPES = new Set([
  "application/vnd.apple.mpegurl",
  "application/x-mpegurl",
  "audio/mpegurl",
  // Zilla sometimes serves manifests without a proper mpegurl content-type
  "text/plain",
]);

function isM3u8(pathname: string, contentType: string): boolean {
  if (pathname.toLowerCase().endsWith(".m3u8")) return true;
  const baseContentType = contentType.toLowerCase().split(";")[0]?.trim() ?? "";
  return M3U8_CONTENT_TYPES.has(baseContentType);
}

function rewriteM3u8(content: string, baseUrl: string): string {
  return content
    .split("\n")
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return line;

      if (trimmed.startsWith("#EXT-X-KEY") || trimmed.startsWith("#EXT-X-MAP")) {
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

  const startedAt = Date.now();
  let upstream: Response;
  try {
    upstream = await fetch(targetUrl.toString(), {
      headers: ZILLA_HEADERS,
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch (error) {
    const isTimeout = error instanceof Error && error.name === "TimeoutError";
    console.error(
      `[animeav1-proxy] fetch failed after ${Date.now() - startedAt}ms for ${targetUrl.pathname}: ${error instanceof Error ? error.message : String(error)}`,
    );
    return NextResponse.json(
      {
        error: isTimeout ? "Upstream timeout" : "Upstream unreachable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 502 },
    );
  }

  console.log(
    `[animeav1-proxy] upstream ${upstream.status} in ${Date.now() - startedAt}ms for ${targetUrl.pathname}`,
  );

  if (!upstream.ok) {
    return NextResponse.json(
      { error: "Upstream error", upstreamStatus: upstream.status, upstreamStatusText: upstream.statusText },
      { status: 502 },
    );
  }

  const contentType = upstream.headers.get("Content-Type") ?? "";

  if (isM3u8(targetUrl.pathname, contentType)) {
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

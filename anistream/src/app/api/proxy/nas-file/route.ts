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

  // Redirect to NAS directly — browser fetches the file without going through
  // the Next.js server, avoiding large-file streaming issues in Route Handlers.
  // The NAS accepts the API key as ?key= for browser-direct requests.
  const redirectUrl = new URL(targetUrl);
  redirectUrl.searchParams.set("key", NAS_API_KEY);

  return NextResponse.redirect(redirectUrl.toString(), { status: 302 });
}

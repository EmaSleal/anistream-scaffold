import { type NextRequest, NextResponse } from "next/server";
import { flaskFetch } from "@/lib/flask-client";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function GET(request: NextRequest, { params }: RouteContext) {
  const { id } = await params;
  const hint = request.nextUrl.searchParams.get("hint");
  const flaskPath = hint
    ? `/api/episodes/watch/${id}/stream-url?hint=${encodeURIComponent(hint)}`
    : `/api/episodes/watch/${id}/stream-url`;
  const res = await flaskFetch(flaskPath);
  const body = await res.json();
  return NextResponse.json(body, { status: res.status });
}

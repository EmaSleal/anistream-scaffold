import { type NextRequest, NextResponse } from "next/server";
import { flaskFetch } from "@/lib/flask-client";

export async function GET(request: NextRequest) {
  const res = await flaskFetch(
    "/api/episodes/recent-simulcast",
    request.nextUrl.searchParams,
  );
  const body = await res.json();
  return NextResponse.json(body, { status: res.status });
}

import { type NextRequest, NextResponse } from "next/server";
import { flaskFetch } from "@/lib/flask-client";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const res = await flaskFetch("/api/series", params);
  const body = await res.json();
  return NextResponse.json(body, { status: res.status });
}

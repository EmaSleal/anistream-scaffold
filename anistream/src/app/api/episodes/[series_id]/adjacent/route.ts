import { type NextRequest, NextResponse } from "next/server";
import { flaskFetch } from "@/lib/flask-client";

interface RouteContext {
  params: Promise<{ series_id: string }>;
}

export async function GET(request: NextRequest, { params }: RouteContext) {
  const { series_id } = await params;
  const searchParams = request.nextUrl.searchParams;
  const res = await flaskFetch(`/api/episodes/${series_id}/adjacent`, searchParams);
  const body = await res.json();
  return NextResponse.json(body, { status: res.status });
}

import { type NextRequest, NextResponse } from "next/server";
import { flaskFetch } from "@/lib/flask-client";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function GET(_request: NextRequest, { params }: RouteContext) {
  const { id } = await params;
  const res = await flaskFetch(`/api/series/${id}/stream-config`);
  const body = await res.json();
  return NextResponse.json(body, { status: res.status });
}

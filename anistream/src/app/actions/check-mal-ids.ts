"use server";

import type { JWT } from "next-auth/jwt";
import { auth } from "@/auth";
import { flaskAuthPost } from "@/lib/flask-client";
import { mintInternalToken } from "@/lib/internal-token";

export async function checkExistingMalIds(malIds: number[]): Promise<number[]> {
  const session = await auth();
  if (session?.user?.role !== "ADMIN") return [];
  if (malIds.length === 0) return [];

  const token: JWT = {
    sub: session.user?.email ?? "unknown",
    role: (session.user as { role?: string })?.role ?? "USER",
  };

  try {
    const internalToken = await mintInternalToken(token);
    const res = await flaskAuthPost(
      "/api/series/check-mal-ids",
      internalToken,
      { mal_ids: malIds },
    );
    if (!res.ok) return [];
    const data = (await res.json()) as { existing: number[] };
    return data.existing ?? [];
  } catch {
    return [];
  }
}

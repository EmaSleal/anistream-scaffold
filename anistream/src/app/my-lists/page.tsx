export const dynamic = "force-dynamic";

import Image from "next/image";
import Link from "next/link";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import type { Series } from "@/types";
import styles from "./my-lists.module.css";
import { ContinueWatchingRow } from "@/components/home/ContinueWatchingRow";
import { SeriesRow } from "@/components/home/SeriesRow";
import { getWatchHistory, getRecentSeries } from "@/app/actions/watchProgress";

export const metadata: Metadata = { title: "My Lists" };

async function getWatchlist(): Promise<Series[]> {
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
  const cookieStore = await cookies();
  const cookieHeader = cookieStore
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");

  const res = await fetch(`${baseUrl}/api/watchlist`, {
    headers: { Cookie: cookieHeader },
    cache: "no-store",
  });

  if (!res.ok) return [];
  return res.json() as Promise<Series[]>;
}

export default async function MyListsPage() {
  // Fetch watchlist and watch history concurrently to avoid a serial waterfall
  const [series, history, recentSeries] = await Promise.all([
    getWatchlist(),
    getWatchHistory(25),
    getRecentSeries(10),
  ]);

  return (
    <div className={styles.page}>
      <h1 className={styles.heading}>My Lists</h1>

      {series.length === 0 ? (
        <p className={styles.empty}>
          Your watchlist is empty. Browse anime and add titles to your list.
        </p>
      ) : (
        <div className={styles.grid}>
          {series.map((s) => (
            <Link key={s.id} href={`/series/${s.id}`} className={styles.card}>
              <div className={styles.thumb}>
                <Image
                  src={s.thumbnailUrl}
                  alt={s.title}
                  fill
                  sizes="(max-width: 768px) 140px, 160px"
                  className={styles.image}
                />
              </div>
              <p className={styles.title}>{s.title}</p>
            </Link>
          ))}
        </div>
      )}
      
      {recentSeries.length > 0 && (
        <SeriesRow title="Recently Watched" series={recentSeries} />
      )}

      {/* Watch history row — ContinueWatchingRow returns null when empty */}
      <ContinueWatchingRow episodes={history} />

      
    </div>
  );
}

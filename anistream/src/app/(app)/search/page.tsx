export const dynamic = "force-dynamic";

import { AnimeCard } from "@/components/home/AnimeCard";
import { getSeriesList } from "@/lib/series";
import { getWatchlistIds } from "@/app/actions/watchlist";
import type { Metadata } from "next";
import styles from "./search.module.css";

export const metadata: Metadata = {
  title: "Search",
  robots: { index: false, follow: false },
};

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = q?.trim() ?? "";

  const [series, watchlistIds] = await Promise.all([
    query.length >= 2 ? getSeriesList({ search: query, limit: 50 }) : Promise.resolve([]),
    getWatchlistIds(),
  ]);

  const watchlistSet = new Set(watchlistIds);

  return (
    <div className="page-content">
      <div className={styles.header}>
        <h1 className={styles.heading}>
          {query ? `Results for "${query}"` : "Search"}
        </h1>
        {query && series.length > 0 && (
          <span className={styles.count}>{series.length} series found</span>
        )}
      </div>

      {series.length > 0 ? (
        <div className={styles.grid} role="list">
          {series.map((s) => (
            <div key={s.id} role="listitem">
              <AnimeCard series={s} isInWatchlist={watchlistSet.has(s.id)} />
            </div>
          ))}
        </div>
      ) : query.length >= 2 ? (
        <div className={styles.empty}>
          <p>No anime found for &ldquo;{query}&rdquo;</p>
        </div>
      ) : null}
    </div>
  );
}

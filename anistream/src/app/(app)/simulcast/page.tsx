export const dynamic = "force-dynamic";

import { auth } from "@/auth";
import { AnimeCard } from "@/components/home/AnimeCard";
import { getSimulcastSeries, consolidateFranchises } from "@/lib/series";
import { getRecentSimulcastEpisodes } from "@/lib/simulcast-episodes";
import { RecentEpisodesRow } from "@/components/simulcast/RecentEpisodesRow";
import { getWatchlistIds } from "@/app/actions/watchlist";
import type { Metadata } from "next";
import styles from "../browse/browse.module.css";
import sc from "./simulcast.module.css";

export const metadata: Metadata = { title: "Simulcasts", robots: { index: false, follow: false } };

export default async function SimulcastPage() {
  const session = await auth();
  const userId = session?.user?.id;

  const [recent, series, watchlistIds] = await Promise.all([
    getRecentSimulcastEpisodes(12, userId),
    getSimulcastSeries(50),
    getWatchlistIds(),
  ]);
  const consolidated = consolidateFranchises(series);
  const watchlistSet = new Set(watchlistIds);

  return (
    <div className="page-content">
      <div className={styles.header}>
        <h1 className={styles.heading}>Simulcasts</h1>
      </div>

      {recent.length > 0 && <RecentEpisodesRow episodes={recent} />}

      {consolidated.length === 0 ? (
        <p className={sc.emptyState}>
          No simulcast series available right now. Check back soon.
        </p>
      ) : (
        <div className={styles.grid} role="list">
          {consolidated.map((s) => (
            <div key={s.id} role="listitem">
              <AnimeCard series={s} isInWatchlist={watchlistSet.has(s.id)} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

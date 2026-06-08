export const dynamic = "force-dynamic";

import { auth } from "@/auth";
import { AnimeCard } from "@/components/home/AnimeCard";
import { getSimulcastSeries, consolidateFranchises } from "@/lib/series";
import { getRecentSimulcastEpisodes } from "@/lib/simulcast-episodes";
import { RecentEpisodesRow } from "./RecentEpisodesRow";
import type { Metadata } from "next";
import styles from "../browse/browse.module.css";
import sc from "./simulcast.module.css";

export const metadata: Metadata = { title: "Simulcasts" };

export default async function SimulcastPage() {
  const session = await auth();
  const userId = session?.user?.id;

  const [recent, series] = await Promise.all([
    getRecentSimulcastEpisodes(12, userId),
    getSimulcastSeries(50),
  ]);
  const consolidated = consolidateFranchises(series);

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
              <AnimeCard series={s} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

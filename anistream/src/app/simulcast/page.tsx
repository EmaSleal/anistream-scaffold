export const dynamic = "force-dynamic";

import { AnimeCard } from "@/components/home/AnimeCard";
import { getSimulcastSeries, consolidateFranchises } from "@/lib/series";
import type { Metadata } from "next";
import styles from "../browse/browse.module.css";

export const metadata: Metadata = { title: "Simulcasts" };

export default async function SimulcastPage() {
  const series = await getSimulcastSeries(50);
  const consolidated = consolidateFranchises(series);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.heading}>Simulcasts</h1>
      </div>

      {consolidated.length === 0 ? (
        <p style={{ color: "var(--color-text-secondary)", fontSize: "1.6rem" }}>
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

import { AnimeCard } from "@/components/home/AnimeCard";
import { getSeriesList } from "@/lib/series";
import type { Metadata } from "next";
import styles from "./browse.module.css";

export const metadata: Metadata = { title: "Browse" };

const FILTER_TABS = ["All Anime", "Simulcasts", "Anime Genres", "Music"] as const;

export default async function BrowsePage() {
  const series = await getSeriesList(50);

  return (
    <div className={styles.page}>
      <nav className={styles.tabs} aria-label="Browse filters">
        {FILTER_TABS.map((tab, i) => (
          <button
            key={tab}
            className={`${styles.tab} ${i === 0 ? styles.tabActive : ""}`}
            aria-current={i === 0 ? "page" : undefined}
          >
            {tab}
          </button>
        ))}
      </nav>

      <div className={styles.header}>
        <h1 className={styles.heading}>Popular</h1>
      </div>

      <div className={styles.grid} role="list">
        {series.map((s) => (
          <div key={s.id} role="listitem">
            <AnimeCard series={s} />
          </div>
        ))}
      </div>
    </div>
  );
}

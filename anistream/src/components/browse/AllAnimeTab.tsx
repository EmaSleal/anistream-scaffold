import { AnimeCard } from "@/components/home/AnimeCard";
import { getSeriesList } from "@/lib/series";
import { getWatchlistIds } from "@/app/actions/watchlist";
import styles from "@/app/(app)/browse/browse.module.css";

export default async function AllAnimeTab() {
  const [series, watchlistIds] = await Promise.all([getSeriesList(50), getWatchlistIds()]);
  const watchlistSet = new Set(watchlistIds);

  return (
    <>
      <div className={styles.header}>
        <h1 className={styles.heading}>Popular</h1>
      </div>
      <div className={styles.grid} role="list">
        {series.map((s) => (
          <div key={s.id} role="listitem">
            <AnimeCard series={s} isInWatchlist={watchlistSet.has(s.id)} />
          </div>
        ))}
      </div>
    </>
  );
}

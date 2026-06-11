import { AnimeCard } from "@/components/home/AnimeCard";
import { getSeriesList } from "@/lib/series";
import styles from "@/app/browse/browse.module.css";

export default async function AllAnimeTab() {
  const series = await getSeriesList(50);
  return (
    <>
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
    </>
  );
}

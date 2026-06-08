import type { Episode } from "@/types";
import { EpisodeCard } from "@/components/shared/EpisodeCard";
import styles from "./ContinueWatchingRow.module.css";

interface ContinueWatchingRowProps {
  episodes: (Episode & { progressSeconds: number })[];
}

export function ContinueWatchingRow({ episodes }: ContinueWatchingRowProps) {
  if (episodes.length === 0) return null;

  return (
    <section className={styles.section}>
      <h2 className={styles.title}>Continue Watching</h2>
      <div className="row-scroll" role="list">
        {episodes.map((ep) => (
          <EpisodeCard
            key={ep.id}
            ep={ep}
            className={styles.cardItem}
            showSeriesTitle
            durationDisplay="remaining"
          />
        ))}
      </div>
    </section>
  );
}

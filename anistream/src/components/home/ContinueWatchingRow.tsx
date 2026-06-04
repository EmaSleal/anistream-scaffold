import Link from "next/link";
import Image from "next/image";
import type { Episode } from "@/types";
import { formatEpisodeLabel, formatDuration } from "@/lib/utils";
import styles from "./ContinueWatchingRow.module.css";

interface ContinueWatchingRowProps {
  episodes: (Episode & { progressSeconds: number })[];
}

export function ContinueWatchingRow({ episodes }: ContinueWatchingRowProps) {
  if (episodes.length === 0) return null;

  return (
    <section className={styles.section}>
      <h2 className={styles.title}>Continue Watching</h2>
      <div className={styles.row} role="list">
        {episodes.map((ep) => {
          const pct = ep.duration > 0 ? (ep.progressSeconds / ep.duration) * 100 : 0;
          return (
            <Link key={ep.id} href={`/watch/${ep.animeflvSlug ?? ep.id}`} className={styles.card} role="listitem">
              <div className={styles.thumb}>
                <Image
                  src={ep.thumbnailUrl}
                  alt={ep.title}
                  fill
                  sizes="200px"
                  className={styles.image}
                />
                <div className={styles.progressBar}>
                  <div className={styles.progressFill} style={{ width: `${pct}%` }} />
                </div>
                <div className={styles.playIcon} aria-hidden="true">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                </div>
              </div>
              <div className={styles.info}>
                <p className={styles.series}>{ep.seriesTitle}</p>
                <p className={styles.episode}>
                  {formatEpisodeLabel(ep.episode, ep.season)} · {formatDuration(ep.duration - ep.progressSeconds)} left
                </p>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

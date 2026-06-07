import Link from "next/link";
import Image from "next/image";
import type { Episode } from "@/types";
import { formatDuration, formatEpisodeLabel, cn } from "@/lib/utils";
import styles from "./EpisodeCard.module.css";

interface EpisodeCardProps {
  ep: Episode;
  className?: string;
  showSeriesTitle?: boolean;
  showSeenBadge?: boolean;
  durationDisplay?: "total" | "remaining";
}

export function EpisodeCard({
  ep,
  className,
  showSeriesTitle = false,
  showSeenBadge = false,
  durationDisplay = "total",
}: EpisodeCardProps) {
  const pct =
    ep.duration > 0 && ep.progressSeconds
      ? (ep.progressSeconds / ep.duration) * 100
      : 0;

  const durationText =
    durationDisplay === "remaining" && ep.progressSeconds
      ? `${formatDuration(ep.duration - ep.progressSeconds)} left`
      : formatDuration(ep.duration);

  return (
    <Link
      href={`/watch/${ep.animeflvSlug ?? ep.id}`}
      className={cn(styles.card, className)}
    >
      <div className={styles.thumb}>
        {ep.thumbnailUrl ? (
          <Image
            src={ep.thumbnailUrl}
            alt={ep.title}
            fill
            sizes="(max-width: 768px) 50vw, 280px"
            className={styles.image}
          />
        ) : (
          <div className={styles.thumbBg} />
        )}
        <div className={styles.playOverlay} aria-hidden="true">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="white">
            <circle cx="12" cy="12" r="12" fill="rgba(0,0,0,0.55)" />
            <polygon points="10 8 16 12 10 16 10 8" fill="white" />
          </svg>
        </div>
        {showSeenBadge && ep.isSeen && (
          <span className={styles.seenBadge}>Visto</span>
        )}
        {pct > 0 && (
          <div className={styles.progressBar}>
            <div className={styles.progressFill} style={{ width: `${pct}%` }} />
          </div>
        )}
      </div>
      <div className={styles.info}>
        {showSeriesTitle ? (
          <>
            <p className={styles.seriesTitle}>{ep.seriesTitle}</p>
            <p className={styles.meta}>
              {formatEpisodeLabel(ep.episode, ep.season)} · {durationText}
            </p>
          </>
        ) : (
          <>
            <p className={styles.label}>
              {formatEpisodeLabel(ep.episode, ep.season)} — {ep.title}
            </p>
            <p className={styles.meta}>
              {durationText} · Sub | Dub
            </p>
          </>
        )}
      </div>
    </Link>
  );
}

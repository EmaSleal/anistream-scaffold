export const dynamic = "force-dynamic";

import { auth } from "@/auth";
import { AnimeCard } from "@/components/home/AnimeCard";
import { getSimulcastSeries, consolidateFranchises } from "@/lib/series";
import { getRecentSimulcastEpisodes } from "@/lib/simulcast-episodes";
import type { RecentEpisode } from "@/lib/simulcast-episodes";
import type { Metadata } from "next";
import styles from "../browse/browse.module.css";
import sc from "./simulcast.module.css";

export const metadata: Metadata = { title: "Simulcasts" };

function formatAiredAt(airedAt: string | undefined): string {
  if (!airedAt) return "";
  try {
    return new Date(airedAt).toLocaleDateString();
  } catch {
    return airedAt;
  }
}

function RecentEpisodeCard({ episode }: { episode: RecentEpisode }) {
  const thumbnail = episode.thumbnailUrl ?? episode.seriesThumbnailUrl;
  const epLabel = episode.title
    ? `Ep. ${episode.episodeNumber} — ${episode.title}`
    : `Ep. ${episode.episodeNumber}`;
  const dateLabel = formatAiredAt(episode.airedAt);
  return (
    <div className={sc.recentCard}>
      {thumbnail && (
        <div className={sc.recentThumb}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={thumbnail}
            alt={episode.seriesTitle}
            className={sc.recentImg}
          />
          {episode.isWatched && (
            <div className={sc.vistoOverlay}>
              <span className={sc.vistoLabel}>VISTO</span>
            </div>
          )}
        </div>
      )}
      <p className={sc.recentTitle} title={episode.seriesTitle}>
        {episode.seriesTitle}
      </p>
      <p className={sc.recentMeta}>{epLabel}</p>
      {dateLabel && <p className={sc.recentDate}>{dateLabel}</p>}
    </div>
  );
}

export default async function SimulcastPage() {
  const session = await auth();
  const userId = session?.user?.id;

  const [recent, series] = await Promise.all([
    getRecentSimulcastEpisodes(12, userId),
    getSimulcastSeries(50),
  ]);
  const consolidated = consolidateFranchises(series);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.heading}>Simulcasts</h1>
      </div>

      {recent.length > 0 && (
        <section className={sc.recentSection}>
          <h2 className={sc.recentHeading}>Recently Aired</h2>
          <div className={sc.recentRow}>
            {recent.map((ep) => (
              <RecentEpisodeCard key={ep.id} episode={ep} />
            ))}
          </div>
        </section>
      )}

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

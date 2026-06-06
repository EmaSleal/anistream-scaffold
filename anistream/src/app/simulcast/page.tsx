export const dynamic = "force-dynamic";

import { auth } from "@/auth";
import { AnimeCard } from "@/components/home/AnimeCard";
import { getSimulcastSeries, consolidateFranchises } from "@/lib/series";
import { getRecentSimulcastEpisodes } from "@/lib/simulcast-episodes";
import type { RecentEpisode } from "@/lib/simulcast-episodes";
import type { Metadata } from "next";
import styles from "../browse/browse.module.css";

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
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.6rem",
        width: "14rem",
        flexShrink: 0,
      }}
    >
      {thumbnail && (
        <div
          style={{
            position: "relative",
            width: "100%",
            aspectRatio: "16/9",
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={thumbnail}
            alt={episode.seriesTitle}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              borderRadius: "0.4rem",
            }}
          />
          {episode.isWatched && (
            <div
              style={{
                position: "absolute",
                inset: 0,
                background: "rgba(0, 0, 0, 0.6)",
                borderRadius: "0.4rem",
                display: "flex",
                alignItems: "flex-start",
                justifyContent: "flex-end",
                padding: "0.5rem",
              }}
            >
              <span
                style={{
                  background: "rgba(0, 0, 0, 0.8)",
                  color: "#fff",
                  padding: "0.3rem 0.6rem",
                  borderRadius: "0.3rem",
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  letterSpacing: "0.05em",
                }}
              >
                VISTO
              </span>
            </div>
          )}
        </div>
      )}
      <p
        style={{
          fontSize: "1.3rem",
          fontWeight: 600,
          margin: 0,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={episode.seriesTitle}
      >
        {episode.seriesTitle}
      </p>
      <p style={{ fontSize: "1.2rem", color: "var(--color-text-secondary)", margin: 0 }}>
        {epLabel}
      </p>
      {dateLabel && (
        <p style={{ fontSize: "1.1rem", color: "var(--color-text-secondary)", margin: 0 }}>
          {dateLabel}
        </p>
      )}
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
        <section style={{ marginBottom: "3.2rem" }}>
          <h2
            style={{
              fontSize: "1.8rem",
              fontWeight: 700,
              marginBottom: "1.6rem",
            }}
          >
            Recently Aired
          </h2>
          <div
            style={{
              display: "flex",
              gap: "1.2rem",
              overflowX: "auto",
              paddingBottom: "0.8rem",
            }}
          >
            {recent.map((ep) => (
              <RecentEpisodeCard key={ep.id} episode={ep} />
            ))}
          </div>
        </section>
      )}

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

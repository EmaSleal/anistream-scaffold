"use client";

import { useRef, useState, useEffect } from "react";
import type { RecentEpisode } from "@/lib/simulcast-episodes";
import sc from "./simulcast.module.css";

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
          <img src={thumbnail} alt={episode.seriesTitle} className={sc.recentImg} />
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

export function RecentEpisodesRow({ episodes }: { episodes: RecentEpisode[] }) {
  const rowRef = useRef<HTMLDivElement>(null);
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(false);

  function updateArrows() {
    const el = rowRef.current;
    if (!el) return;
    setCanLeft(el.scrollLeft > 4);
    setCanRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 4);
  }

  useEffect(() => {
    const el = rowRef.current;
    if (!el) return;
    updateArrows();
    el.addEventListener("scroll", updateArrows, { passive: true });
    const ro = new ResizeObserver(updateArrows);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", updateArrows);
      ro.disconnect();
    };
  }, [episodes]);

  function scroll(dir: "left" | "right") {
    rowRef.current?.scrollBy({ left: dir === "left" ? -480 : 480, behavior: "smooth" });
  }

  return (
    <section className={sc.recentSection}>
      <h2 className={sc.recentHeading}>Recently Aired</h2>
      <div className={sc.rowWrapper}>
        <button
          className={`${sc.arrow} ${sc.arrowLeft} ${canLeft ? sc.arrowVisible : ""}`}
          onClick={() => scroll("left")}
          aria-label="Scroll left"
          tabIndex={-1}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>

        <div className={sc.recentRow} ref={rowRef}>
          {episodes.map((ep) => (
            <RecentEpisodeCard key={ep.id} episode={ep} />
          ))}
        </div>

        <button
          className={`${sc.arrow} ${sc.arrowRight} ${canRight ? sc.arrowVisible : ""}`}
          onClick={() => scroll("right")}
          aria-label="Scroll right"
          tabIndex={-1}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      </div>
    </section>
  );
}

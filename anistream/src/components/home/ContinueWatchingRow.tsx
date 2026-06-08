"use client";

import { useRef, useState, useEffect } from "react";
import type { Episode } from "@/types";
import { EpisodeCard } from "@/components/shared/EpisodeCard";
import styles from "./ContinueWatchingRow.module.css";

interface ContinueWatchingRowProps {
  episodes: (Episode & { progressSeconds: number })[];
}

export function ContinueWatchingRow({ episodes }: ContinueWatchingRowProps) {
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

  if (episodes.length === 0) return null;

  return (
    <section className={styles.section}>
      <h2 className={styles.title}>Continue Watching</h2>
      <div className={styles.wrapper}>
        <button
          className={`${styles.arrow} ${styles.arrowLeft} ${canLeft ? styles.arrowVisible : ""}`}
          onClick={() => scroll("left")}
          aria-label="Scroll left"
          tabIndex={-1}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>

        <div className={`row-scroll ${styles.row}`} ref={rowRef} role="list">
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

        <button
          className={`${styles.arrow} ${styles.arrowRight} ${canRight ? styles.arrowVisible : ""}`}
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

"use client";

import { useState, useTransition } from "react";
import Image from "next/image";
import type { Series } from "@/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { toggleWatchlist } from "@/app/actions/watchlist";
import { cn } from "@/lib/utils";
import styles from "./HeroBanner.module.css";

interface HeroBannerProps {
  featured: Series[];
  watchlistIds: string[];
}

export function HeroBanner({ featured, watchlistIds }: HeroBannerProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [optimisticIds, setOptimisticIds] = useState<string[]>(watchlistIds);
  const [isPending, startTransition] = useTransition();
  const current = featured[activeIndex];

  if (!current) return null;

  const inList = optimisticIds.includes(current.id);

  function handleToggle() {
    const next = inList
      ? optimisticIds.filter((id) => id !== current.id)
      : [...optimisticIds, current.id];
    setOptimisticIds(next);
    startTransition(() => toggleWatchlist(current.id));
  }

  return (
    <section className={styles.hero} aria-label="Featured anime">
      <div className={styles.backdrop}>
        <Image
          src={current.bannerUrl}
          alt=""
          fill
          priority
          sizes="100vw"
          className={styles.backdropImage}
        />
        <div className={styles.gradientLeft} aria-hidden="true" />
        <div className={styles.gradientBottom} aria-hidden="true" />
      </div>

      <div className={styles.content}>
        <div className={styles.meta}>
          <Badge variant="rating">{current.rating}</Badge>
          <span className={styles.formats}>
            {current.audioFormats.map((f) =>
              f === "dub" ? "Dub" : f === "sub" ? "Sub" : "Dub | Sub"
            ).join(" | ")}
          </span>
          <span className={styles.genreDot}>·</span>
          <span className={styles.genres}>
            {current.genres.slice(0, 4).join(", ")}
          </span>
        </div>

        <h1 className={styles.title}>{current.title}</h1>
        <p className={styles.description}>{current.description}</p>

        <div className={styles.actions}>
          <Button
            variant="primary"
            size="lg"
            aria-label={`Start watching ${current.title}`}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
            Start Watching E1
          </Button>
          <button
            className={cn(styles.bookmarkBtn, inList && styles.bookmarked)}
            onClick={handleToggle}
            disabled={isPending}
            aria-label={inList ? "Remove from watchlist" : "Add to watchlist"}
            aria-pressed={inList}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill={inList ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z" />
            </svg>
          </button>
        </div>
      </div>

      {featured.length > 1 && (
        <div className={styles.dots} role="tablist" aria-label="Featured anime slides">
          {featured.map((s, i) => (
            <button
              key={s.id}
              role="tab"
              aria-selected={i === activeIndex}
              aria-label={`View ${s.title}`}
              className={cn(styles.dot, i === activeIndex && styles.dotActive)}
              onClick={() => setActiveIndex(i)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

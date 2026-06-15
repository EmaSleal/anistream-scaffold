"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import { signIn } from "next-auth/react";
import type { Series } from "@/types";
import styles from "./LandingHero.module.css";
import { cn } from "@/lib/utils";

interface LandingHeroProps {
  series: Series[];
}

export function LandingHero({ series }: LandingHeroProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const current = series[activeIndex];

  // Auto-advance every 5s; restarts whenever activeIndex changes (manual or auto)
  useEffect(() => {
    const id = setTimeout(() => {
      setActiveIndex((i) => (i + 1) % series.length);
    }, 5000);
    return () => clearTimeout(id);
  }, [activeIndex, series.length]);

  if (!current) return null;

  return (
    <section className={styles.hero} aria-label="Featured anime">
      <div className={styles.backdrop}>
        <Image
          src={current.bannerUrl}
          alt=""
          fill
          priority
          sizes="100vw"
          className={styles.backdropImg}
        />
        <div className={styles.gradientLeft} aria-hidden="true" />
        <div className={styles.gradientBottom} aria-hidden="true" />
      </div>

      <div className={styles.content}>
        <div className={styles.meta}>
          {current.rating && (
            <span className={styles.rating}>{current.rating}</span>
          )}
          <span className={styles.genres}>
            {current.genres.slice(0, 3).join(" · ")}
          </span>
        </div>

        <h1 className={styles.title}>{current.title}</h1>
        <p className={styles.description}>{current.description}</p>

        <button
          className={styles.cta}
          onClick={() => signIn("google")}
          type="button"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
          Watch Now — Sign In Free
        </button>
      </div>

      {series.length > 1 && (
        <div className={styles.dots} role="tablist" aria-label="Featured anime slides">
          {series.map((s, i) => (
            <button
              key={s.id}
              role="tab"
              aria-selected={i === activeIndex}
              aria-label={`View ${s.title}`}
              className={cn(styles.dot, i === activeIndex && styles.dotActive)}
              onClick={() => setActiveIndex(i)}
            >
              {i === activeIndex && (
                <span key={activeIndex} className={styles.dotFill} aria-hidden="true" />
              )}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

"use client";

import { useRef, useState, useEffect } from "react";
import type { Series } from "@/types";
import { MarketingCard } from "@/components/marketing/MarketingCard";
import styles from "./CatalogRow.module.css";

interface CatalogRowProps {
  series: Series[];
}

export function CatalogRow({ series }: CatalogRowProps) {
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
  }, [series]);

  function scroll(dir: "left" | "right") {
    rowRef.current?.scrollBy({ left: dir === "left" ? -480 : 480, behavior: "smooth" });
  }

  return (
    <section id="catalog" className={styles.section}>
      <div className={styles.container}>
        <h2 className={styles.heading}>Popular Right Now</h2>
        <div className={styles.cardsWrapper}>
          <button
            className={`${styles.arrow} ${styles.arrowLeft} ${canLeft ? styles.arrowVisible : ""}`}
            onClick={() => scroll("left")}
            aria-label="Scroll left"
            tabIndex={-1}
            type="button"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>

          <div className={styles.cardsRow} ref={rowRef}>
            {series.map((s) => (
              <MarketingCard key={s.id} series={s} />
            ))}
          </div>

          <button
            className={`${styles.arrow} ${styles.arrowRight} ${canRight ? styles.arrowVisible : ""}`}
            onClick={() => scroll("right")}
            aria-label="Scroll right"
            tabIndex={-1}
            type="button"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>
      </div>
    </section>
  );
}

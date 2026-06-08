"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Select } from "@/components/ui/Select";
import styles from "./filterBar.module.css";

export interface FilterBarProps {
  title?: string;
  genres: string[];
  activeGenre?: string;
  activeYear?: string;
  activeSeason?: string;
}

const SEASONS = ["Winter", "Spring", "Summer", "Fall"] as const;

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = Array.from({ length: CURRENT_YEAR - 2019 }, (_, i) => {
  const y = CURRENT_YEAR - i;
  return { label: String(y), value: String(y) };
});

export function FilterBar({ title = "Discover", genres, activeGenre, activeYear, activeSeason }: FilterBarProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const hasActiveFilter = Boolean(activeGenre || activeYear || activeSeason);
  const [isOpen, setIsOpen] = useState(hasActiveFilter);

  function setParam(key: string, value: string | null) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "genres");
    if (value === null || value === "") {
      params.delete(key);
    } else {
      params.set(key, value);
    }
    router.push(`/browse?${params.toString()}`);
  }

  const activeCount = [activeGenre, activeYear, activeSeason].filter(Boolean).length;

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <h1 className={styles.title}>{title}</h1>
        <button
          className={`${styles.toggle} ${isOpen ? styles.toggleOpen : ""}`}
          onClick={() => setIsOpen((o) => !o)}
          aria-expanded={isOpen}
          aria-controls="filter-accordion"
        >
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className={styles.toggleIcon}>
            <path d="M2 4.5h12M4.5 8h7M7 11.5h2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          Filters
          {activeCount > 0 && (
            <span className={styles.badge}>{activeCount}</span>
          )}
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className={styles.chevron}>
            <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      <div
        id="filter-accordion"
        className={`${styles.accordion} ${isOpen ? styles.accordionOpen : ""}`}
      >
        <div className={styles.accordionContent}>
          {genres.length > 0 && (
            <div className={styles.filterRow}>
              <span className={`label-caps ${styles.filterLabelWidth}`}>Genre</span>
              <div className={styles.chips}>
                {genres.map((genre) => {
                  const isActive = genre === activeGenre;
                  return (
                    <button
                      key={genre}
                      className={`${styles.chip} ${isActive ? styles.chipActive : ""}`}
                      onClick={() => setParam("genre", isActive ? null : genre)}
                      aria-pressed={isActive}
                    >
                      {genre}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div className={styles.filterRow}>
            <span className={`label-caps ${styles.filterLabelWidth}`}>Year</span>
            <Select
              options={YEAR_OPTIONS}
              placeholder="Any year"
              value={activeYear ?? ""}
              onChange={(val) => setParam("year", val || null)}
              aria-label="Filter by year"
            />
          </div>

          <div className={styles.filterRow}>
            <span className={`label-caps ${styles.filterLabelWidth}`}>Season</span>
            <div className={styles.chips}>
              {SEASONS.map((season) => {
                const value = season.toLowerCase();
                const isActive = value === activeSeason;
                return (
                  <button
                    key={season}
                    className={`${styles.chip} ${isActive ? styles.chipActive : ""}`}
                    onClick={() => setParam("season", isActive ? null : value)}
                    aria-pressed={isActive}
                  >
                    {season}
                  </button>
                );
              })}
            </div>
          </div>

          {hasActiveFilter && (
            <div className={styles.filterRow}>
              <button
                className={styles.clearBtn}
                onClick={() => {
                  const params = new URLSearchParams();
                  params.set("tab", "genres");
                  router.push(`/browse?${params.toString()}`);
                }}
              >
                Clear filters
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import type { Series } from "@/types";
import styles from "./SeriesDetailsToggle.module.css";

interface SeriesDetailsToggleProps {
  series: Series;
  audioLanguages: string;
}

export function SeriesDetailsToggle({ series, audioLanguages }: SeriesDetailsToggleProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <button
        className={styles.toggle}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        {expanded ? "MENOS DETALLES" : "VER MÁS DETALLES"}
        <svg
          width="12" height="12" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2.5"
          aria-hidden="true"
          style={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {expanded && (
        <div className={styles.details}>
          <div className={styles.col}>
            <p className={styles.description}>{series.description}</p>
          </div>
          <div className={styles.col}>
            <div className={styles.row}>
              <span className={styles.label}>Audio</span>
              <span className={styles.value}>{audioLanguages}</span>
            </div>
            <div className={styles.row}>
              <span className={styles.label}>Subtítulos</span>
              <span className={styles.value}>Español (América Latina), English, Deutsch, Français</span>
            </div>
            <div className={styles.row}>
              <span className={styles.label}>Géneros</span>
              <span className={styles.value}>
                {series.genres.join(", ")}
              </span>
            </div>
            <div className={styles.row}>
              <span className={styles.label}>Aviso sobre el contenido</span>
              <span className={styles.value}>
                <span className={styles.ratingBadge}>{series.rating}</span>{" "}
                Violencia, Lenguaje ofensivo
              </span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

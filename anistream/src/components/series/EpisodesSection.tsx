"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import type { Episode } from "@/types";
import { formatDuration, formatEpisodeLabel } from "@/lib/utils";
import styles from "./EpisodesSection.module.css";

interface Season {
  label: string;
  episodes: Episode[];
}

interface EpisodesSectionProps {
  seasons: Season[];
  initialSeasonIdx?: number;
}

function EpisodeCard({ ep }: { ep: Episode }) {
  const pct = ep.duration > 0 && ep.progressSeconds
    ? (ep.progressSeconds / ep.duration) * 100
    : 0;

  return (
    <Link href={`/watch/${ep.animeflvSlug ?? ep.id}`} className={styles.epCard}>
      <div className={styles.epThumb}>
        {ep.thumbnailUrl ? (
          <Image
            src={ep.thumbnailUrl}
            alt={ep.title}
            fill
            sizes="(max-width: 768px) 50vw, 280px"
            className={styles.epThumbImg}
          />
        ) : (
          <div className={styles.epThumbBg} />
        )}
        <div className={styles.playOverlay} aria-hidden="true">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="white">
            <circle cx="12" cy="12" r="12" fill="rgba(0,0,0,0.55)" />
            <polygon points="10 8 16 12 10 16 10 8" fill="white" />
          </svg>
        </div>
        {ep.isSeen && <span className={styles.seenBadge}>Visto</span>}
        {pct > 0 && !ep.isSeen && (
          <div className={styles.progressBar}>
            <div className={styles.progressFill} style={{ width: `${pct}%` }} />
          </div>
        )}
      </div>
      <div className={styles.epInfo}>
        <p className={styles.epLabel}>
          {formatEpisodeLabel(ep.episode, ep.season)} — {ep.title}
        </p>
        <p className={styles.epMeta}>
          {formatDuration(ep.duration)} · Sub | Dub
        </p>
      </div>
    </Link>
  );
}

export function EpisodesSection({ seasons, initialSeasonIdx = 0 }: EpisodesSectionProps) {
  if (seasons.length === 0) return null;

  const [seasonIdx, setSeasonIdx] = useState(initialSeasonIdx);
  const [oldest, setOldest] = useState(true);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [selectOpen, setSelectOpen] = useState(false);
  const optionsRef = useRef<HTMLDivElement>(null);

  const current = seasons[seasonIdx];
  const episodes = oldest ? current.episodes : [...current.episodes].reverse();

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (optionsRef.current && !optionsRef.current.contains(e.target as Node)) {
        setOptionsOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <section className={styles.section}>
      <div className={styles.controls}>
        <div className={styles.seasonWrap}>
          <button
            className={styles.seasonBtn}
            onClick={() => setSelectOpen((v) => !v)}
            aria-expanded={selectOpen}
          >
            {current.label}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          {selectOpen && (
            <div className={styles.seasonDropdown}>
              {seasons.map((s, i) => (
                <button
                  key={`${s.label}-${i}`}
                  className={`${styles.seasonOption} ${i === seasonIdx ? styles.seasonOptionActive : ""}`}
                  onClick={() => { setSeasonIdx(i); setSelectOpen(false); }}
                >
                  {s.label}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className={styles.right}>
          <button
            className={styles.sortBtn}
            onClick={() => setOldest((v) => !v)}
            aria-label="Toggle sort order"
          >
            {oldest ? "LO MÁS ANTIGUO" : "LO MÁS NUEVO"}
          </button>

          <span className={styles.divider} aria-hidden="true" />

          <div className={styles.optionsWrap} ref={optionsRef}>
            <button
              className={styles.sortBtn}
              onClick={() => setOptionsOpen((v) => !v)}
              aria-expanded={optionsOpen}
            >
              OPCIONES
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
            {optionsOpen && (
              <div className={styles.optionsDropdown}>
                <button
                  className={styles.optionItem}
                  onClick={() => setOptionsOpen(false)}
                >
                  Marcar la temporada como vista
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className={styles.grid}>
        {episodes.map((ep) => (
          <EpisodeCard key={ep.id} ep={ep} />
        ))}
      </div>

      <div className={styles.pagination}>
        <button
          className={styles.pageBtn}
          disabled={seasonIdx === 0}
          onClick={() => setSeasonIdx((i) => i - 1)}
        >
          ← ANTERIOR TEMPORADA
        </button>
        <button
          className={styles.pageBtn}
          disabled={seasonIdx === seasons.length - 1}
          onClick={() => setSeasonIdx((i) => i + 1)}
        >
          SIGUIENTE TEMPORADA →
        </button>
      </div>
    </section>
  );
}

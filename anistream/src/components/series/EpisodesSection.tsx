"use client";

import { useState, useRef, useEffect } from "react";
import type { Episode } from "@/types";
import { EpisodeCard } from "@/components/shared/EpisodeCard";
import {
  enqueueErrorMessage,
  enqueueSeries,
  fetchDownloadedEpisodes,
  fetchSeriesQueue,
  summarizeQueue,
  type QueueSummary,
} from "@/lib/downloads-client";
import { partsOf, selectPart, showPartTabs, type SeasonPart } from "./seasonParts";
import styles from "./EpisodesSection.module.css";

interface Season {
  label: string;
  mediaType?: string | null;
  seriesId?: string;
  episodes: Episode[];
  parts?: SeasonPart<Episode>[];
}

interface EpisodesSectionProps {
  seasons: Season[];
  initialSeasonIdx?: number;
  initialPartIdx?: number;
  isAdmin?: boolean;
}

type SeasonGroup = "tv" | "movie" | "ova" | "special";

const QUEUE_POLL_MS = 5000;

const GROUP_ORDER: SeasonGroup[] = ["tv", "movie", "ova", "special"];

const GROUP_LABELS: Record<SeasonGroup, string> = {
  tv: "Temporadas",
  movie: "Películas",
  ova: "OVAs",
  special: "Especiales",
};

// Mirrors the backend's season_label() fallback (scraper/domain/series.py):
// any unrecognized media_type defaults to a TV "Temporada N" label, so it
// must default to the "tv" group here too — otherwise it lands in neither
// its own group nor "Temporadas", becoming invisible in the dropdown.
function groupOf(mediaType?: string | null): SeasonGroup {
  const mt = (mediaType || "tv").toLowerCase();
  if (mt === "movie") return "movie";
  if (mt === "ova" || mt === "ona") return "ova";
  if (mt === "special") return "special";
  return "tv";
}

export function EpisodesSection({
  seasons,
  initialSeasonIdx = 0,
  initialPartIdx = 0,
  isAdmin = false,
}: EpisodesSectionProps) {
  const [seasonIdx, setSeasonIdx] = useState(initialSeasonIdx);
  const [partIdx, setPartIdx] = useState(initialPartIdx);
  const changeSeason = (idx: number) => {
    setSeasonIdx(idx);
    setPartIdx(0);
  };
  const [oldest, setOldest] = useState(true);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [selectOpen, setSelectOpen] = useState(false);
  const optionsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (optionsRef.current && !optionsRef.current.contains(e.target as Node)) {
        setOptionsOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // The selected part's own series: admin download/queue actions target it.
  const selected = seasons[seasonIdx] ? selectPart(seasons[seasonIdx], partIdx) : null;
  const seriesId = selected?.seriesId;
  const [downloaded, setDownloaded] = useState<Set<number>>(new Set());
  const [downloadedLoaded, setDownloadedLoaded] = useState(false);
  const [queue, setQueue] = useState<QueueSummary | null>(null);
  const [enqueueing, setEnqueueing] = useState(false);
  const [enqueueError, setEnqueueError] = useState<string | null>(null);
  // Bumped to (re)start queue polling: on mount, after enqueueing a series.
  const [pollKey, setPollKey] = useState(0);

  useEffect(() => {
    setDownloaded(new Set());
    setDownloadedLoaded(false);
    if (!seriesId) return;
    let cancelled = false;
    fetchDownloadedEpisodes(seriesId).then((nums) => {
      if (cancelled) return;
      setDownloaded(new Set(nums));
      setDownloadedLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, [seriesId]);

  // Admin only: poll the series queue while items are queued/downloading and
  // refresh the downloaded icons (from the fresh list the queue response carries)
  // whenever the number of finished items grows.
  useEffect(() => {
    setQueue(null);
    if (!isAdmin || !seriesId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let lastDone = -1;

    const tick = async () => {
      const { items, downloadedEpisodes } = await fetchSeriesQueue(seriesId);
      if (cancelled) return;
      const summary = summarizeQueue(items);
      setQueue(summary);
      const done = items.filter((i) => i.status === "done").length;
      if (lastDone !== -1 && done > lastDone && downloadedEpisodes) {
        setDownloaded(new Set(downloadedEpisodes));
      }
      lastDone = done;
      if (summary.active) timer = setTimeout(tick, QUEUE_POLL_MS);
    };
    tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [isAdmin, seriesId, pollKey]);

  const handleDownloadSeries = async () => {
    if (!seriesId || enqueueing) return;
    setEnqueueing(true);
    setEnqueueError(null);
    try {
      await enqueueSeries(seriesId);
      setPollKey((k) => k + 1);
    } catch (err) {
      // Leave the button available so the admin can retry.
      setEnqueueError(enqueueErrorMessage(err));
    } finally {
      setEnqueueing(false);
    }
  };

  if (seasons.length === 0) return null;

  const current = seasons[seasonIdx];
  const partEpisodes = selected!.part.episodes;
  const episodes = oldest ? partEpisodes : [...partEpisodes].reverse();

  const downloadedCount = partEpisodes.filter((e) => downloaded.has(e.episode)).length;
  const allDownloaded = partEpisodes.length > 0 && downloadedCount === partEpisodes.length;
  const showDownloadBtn =
    isAdmin && !!seriesId && downloadedLoaded && partEpisodes.length > 0 && !allDownloaded;
  const queueLabel =
    queue && queue.active
      ? `En cola: ${queue.queued}` +
        (queue.downloadingEpisode !== null
          ? ` · Descargando E${String(queue.downloadingEpisode).padStart(2, "0")}`
          : "") +
        (queue.failed > 0 ? ` · Fallidos: ${queue.failed}` : "")
      : null;

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
              {GROUP_ORDER.map((group) => {
                const items = seasons
                  .map((s, i) => ({ s, i }))
                  .filter(({ s }) => groupOf(s.mediaType) === group);
                if (items.length === 0) return null;
                return (
                  <div key={group} className={styles.seasonGroup}>
                    <div className={styles.seasonGroupHeader}>{GROUP_LABELS[group]}</div>
                    {items.map(({ s, i }) => (
                      <button
                        key={`${s.label}-${i}`}
                        className={`${styles.seasonOption} ${i === seasonIdx ? styles.seasonOptionActive : ""}`}
                        onClick={() => { changeSeason(i); setSelectOpen(false); }}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className={styles.right}>
          {isAdmin && queueLabel && (
            <span className={styles.queueStatus} role="status">
              {queueLabel}
            </span>
          )}
          {showDownloadBtn && enqueueError && (
            <span className={styles.enqueueError} role="alert">
              {enqueueError}
            </span>
          )}
          {showDownloadBtn && (
            <>
              <button
                className={styles.sortBtn}
                onClick={handleDownloadSeries}
                disabled={enqueueing || !!queue?.active}
              >
                {downloadedCount === 0 ? "Descargar serie" : "Terminar de descargar serie"}
              </button>
              <span className={styles.divider} aria-hidden="true" />
            </>
          )}
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

      {showPartTabs(current) && (
        <div className={styles.partTabs} role="tablist">
          {partsOf(current).map((p, i) => (
            <button
              key={`${p.seriesId}-${i}`}
              role="tab"
              aria-selected={i === selected!.partIdx}
              className={`${styles.partTab} ${i === selected!.partIdx ? styles.partTabActive : ""}`}
              onClick={() => setPartIdx(i)}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}

      <div className={styles.grid}>
        {episodes.map((ep) => (
          <EpisodeCard
            key={ep.id}
            ep={ep}
            showSeenBadge
            isAdmin={isAdmin}
            isDownloaded={downloaded.has(ep.episode)}
          />
        ))}
      </div>

      <div className={styles.pagination}>
        <button
          className={styles.pageBtn}
          disabled={seasonIdx === 0}
          onClick={() => changeSeason(seasonIdx - 1)}
        >
          ← ANTERIOR TEMPORADA
        </button>
        <button
          className={styles.pageBtn}
          disabled={seasonIdx === seasons.length - 1}
          onClick={() => changeSeason(seasonIdx + 1)}
        >
          SIGUIENTE TEMPORADA →
        </button>
      </div>
    </section>
  );
}

"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import styles from "./DownloadsManager.module.css";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type EpisodeStatus = "downloaded" | "missing" | "unknown" | "loading";
type JobPhase = "pending" | "downloading" | "done" | "failed" | "unknown";

interface Source {
  source: "jkanime";
  available: boolean;
}

interface JobState {
  jobId: string;
  phase: JobPhase;
  error?: string;
}

interface Episode {
  episodeNumber: number;
  title: string;
}

interface SeriesMeta {
  id: string;
  title: string;
  slug: string;
}

type SeriesDownloadStatus = "all" | "partial" | "none" | "unknown";

interface SeriesOverviewRow {
  id: string;
  title: string;
  jkanimeIngested: boolean;
  episodeCount: number;
  downloadedCount: number;
  status: SeriesDownloadStatus;
}

interface State {
  series: SeriesMeta | null;
  episodes: Episode[];
  statusByEp: Record<number, EpisodeStatus>;
  sourcesByEp: Record<number, Source[] | "loading">;
  selectedSourceByEp: Record<number, string>;
  jobByEp: Record<number, JobState>;
  error: string | null;
}

type Action =
  | { type: "SELECT_SERIES"; series: SeriesMeta; episodes: Episode[] }
  | { type: "SET_STATUSES"; statuses: Record<number, EpisodeStatus> }
  | { type: "SET_SOURCES"; ep: number; sources: Source[] }
  | { type: "SOURCES_LOADING"; ep: number }
  | { type: "SELECT_SOURCE"; ep: number; source: string }
  | { type: "JOB_STARTED"; ep: number; jobId: string }
  | { type: "JOB_UPDATED"; ep: number; phase: JobPhase; error?: string }
  | { type: "ERROR"; message: string }
  | { type: "CLEAR_ERROR" };

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

function initialState(): State {
  return {
    series: null,
    episodes: [],
    statusByEp: {},
    sourcesByEp: {},
    selectedSourceByEp: {},
    jobByEp: {},
    error: null,
  };
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "SELECT_SERIES":
      return {
        ...initialState(),
        series: action.series,
        episodes: action.episodes,
        statusByEp: Object.fromEntries(
          action.episodes.map((ep) => [ep.episodeNumber, "loading" as EpisodeStatus])
        ),
      };
    case "SET_STATUSES":
      return { ...state, statusByEp: { ...state.statusByEp, ...action.statuses } };
    case "SOURCES_LOADING":
      return { ...state, sourcesByEp: { ...state.sourcesByEp, [action.ep]: "loading" } };
    case "SET_SOURCES":
      return { ...state, sourcesByEp: { ...state.sourcesByEp, [action.ep]: action.sources } };
    case "SELECT_SOURCE":
      return {
        ...state,
        selectedSourceByEp: { ...state.selectedSourceByEp, [action.ep]: action.source },
      };
    case "JOB_STARTED":
      return {
        ...state,
        jobByEp: {
          ...state.jobByEp,
          [action.ep]: { jobId: action.jobId, phase: "pending" },
        },
      };
    case "JOB_UPDATED":
      return {
        ...state,
        jobByEp: {
          ...state.jobByEp,
          [action.ep]: {
            jobId: state.jobByEp[action.ep]?.jobId ?? "",
            phase: action.phase,
            error: action.error,
          },
        },
        statusByEp:
          action.phase === "done"
            ? { ...state.statusByEp, [action.ep]: "downloaded" }
            : state.statusByEp,
      };
    case "ERROR":
      return { ...state, error: action.message };
    case "CLEAR_ERROR":
      return { ...state, error: null };
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function fetchSeriesSearch(q: string): Promise<SeriesMeta[]> {
  if (!q.trim()) return [];
  const res = await fetch(
    `/api/series/search?q=${encodeURIComponent(q)}&limit=10`,
    { cache: "no-store" }
  );
  if (!res.ok) return [];
  const data = await res.json().catch(() => []);
  const list = Array.isArray(data) ? data : (data.series ?? []);
  return list.map((s: Record<string, unknown>) => ({
    id: String(s.id ?? ""),
    title: String(s.title ?? ""),
    slug: String(s.slug ?? s.id ?? ""),
  }));
}

interface RawEpisode {
  episode_number: number;
  title: string;
  status: string;
}

async function fetchEpisodeStatuses(
  seriesId: string
): Promise<{ episodes: { episodeNumber: number; title: string; status: string }[] }> {
  const res = await fetch(`/api/admin/downloads/episodes/${seriesId}`, {
    cache: "no-store",
  });
  if (!res.ok) return { episodes: [] };
  const data = await res.json().catch(() => ({ episodes: [] }));
  return {
    episodes: (data.episodes ?? []).map((e: RawEpisode) => ({
      episodeNumber: e.episode_number,
      title: e.title ?? "",
      status: e.status ?? "unknown",
    })),
  };
}

async function fetchSeriesOverview(
  q: string,
  limit: number,
  offset: number
): Promise<{ series: SeriesOverviewRow[]; total: number }> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (q.trim()) params.set("q", q.trim());

  const res = await fetch(`/api/admin/downloads/series-overview?${params}`, {
    cache: "no-store",
  });
  if (!res.ok) return { series: [], total: 0 };
  const data = await res.json().catch(() => ({}));
  return { series: data.series ?? [], total: data.total ?? 0 };
}

async function fetchSources(seriesId: string, ep: number): Promise<Source[]> {
  const res = await fetch(
    `/api/admin/downloads/sources/${seriesId}?episode_number=${ep}`,
    { cache: "no-store" }
  );
  if (!res.ok) return [];
  const data = await res.json().catch(() => ({}));
  return data.sources ?? [];
}

async function triggerDownload(
  seriesId: string,
  ep: number,
  source: string
): Promise<{ jobId: string; status: JobPhase }> {
  const res = await fetch("/api/admin/downloads/trigger", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ series_id: seriesId, episode_number: ep, source }),
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error ?? `HTTP ${res.status}`);
  }
  return res.json();
}

async function pollJob(jobId: string): Promise<{ status: JobPhase; error?: string }> {
  const res = await fetch(`/api/admin/downloads/jobs/${jobId}`, { cache: "no-store" });
  if (!res.ok) return { status: "unknown" };
  return res.json().catch(() => ({ status: "unknown" }));
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: EpisodeStatus }) {
  if (status === "loading")
    return <span className={`${styles.badge} ${styles.badgeLoading}`}>loading…</span>;
  if (status === "downloaded")
    return <span className={`${styles.badge} ${styles.badgeDownloaded}`}>Downloaded</span>;
  if (status === "missing")
    return <span className={`${styles.badge} ${styles.badgeMissing}`}>Not downloaded</span>;
  return <span className={`${styles.badge} ${styles.badgeUnknown}`}>Unknown</span>;
}

function JobStatusLabel({ job }: { job: JobState | undefined }) {
  if (!job) return null;
  const cls =
    job.phase === "pending"
      ? styles.jobPending
      : job.phase === "downloading"
      ? styles.jobDownloading
      : job.phase === "done"
      ? styles.jobDone
      : job.phase === "failed"
      ? styles.jobFailed
      : styles.jobUnknown;

  return (
    <span className={`${styles.jobStatus} ${cls}`}>
      {job.phase === "pending" && "Queued…"}
      {job.phase === "downloading" && "Downloading…"}
      {job.phase === "done" && "Done"}
      {job.phase === "failed" && `Failed: ${job.error ?? "unknown error"}`}
      {job.phase === "unknown" && "Status unknown"}
    </span>
  );
}

// ---------------------------------------------------------------------------
// EpisodeRow
// ---------------------------------------------------------------------------

interface EpisodeRowProps {
  ep: Episode;
  status: EpisodeStatus;
  sources: Source[] | "loading" | undefined;
  selectedSource: string | undefined;
  job: JobState | undefined;
  seriesId: string;
  onExpand: (ep: number) => void;
  onSelectSource: (ep: number, source: string) => void;
  onTrigger: (ep: number) => void;
}

function EpisodeRow({
  ep,
  status,
  sources,
  selectedSource,
  job,
  onExpand,
  onSelectSource,
  onTrigger,
}: EpisodeRowProps) {
  const isDownloaded = status === "downloaded";
  const hasJob = !!job;
  const jobActive = hasJob && (job.phase === "pending" || job.phase === "downloading");
  const jobTerminal = hasJob && (job.phase === "done" || job.phase === "failed");

  const availableSources =
    sources && sources !== "loading" ? sources.filter((s) => s.available) : [];

  const showActions = !isDownloaded && !jobTerminal;

  return (
    <tr>
      <td>{ep.episodeNumber}</td>
      <td>{ep.title || `Episode ${ep.episodeNumber}`}</td>
      <td>
        <StatusBadge status={status} />
      </td>
      <td>
        {showActions && (
          <div className={styles.actions}>
            {sources === undefined && (
              <button
                className={`${styles.triggerBtn} ${styles.triggerBtnSecondary}`}
                onClick={() => onExpand(ep.episodeNumber)}
              >
                Check sources
              </button>
            )}
            {sources === "loading" && (
              <span className={`${styles.badge} ${styles.badgeLoading}`}>loading…</span>
            )}
            {sources && sources !== "loading" && (
              <>
                {availableSources.length === 0 ? (
                  <span className={`${styles.badge} ${styles.badgeUnknown}`}>No source available</span>
                ) : (
                  <>
                    <select
                      className={styles.sourceSelect}
                      value={selectedSource ?? availableSources[0]?.source ?? ""}
                      onChange={(e) => onSelectSource(ep.episodeNumber, e.target.value)}
                      disabled={jobActive}
                    >
                      {availableSources.map((s) => (
                        <option key={s.source} value={s.source}>
                          JKAnime
                        </option>
                      ))}
                    </select>
                    <button
                      className={styles.triggerBtn}
                      onClick={() => onTrigger(ep.episodeNumber)}
                      disabled={jobActive || !availableSources.length}
                    >
                      Download
                    </button>
                  </>
                )}
              </>
            )}
            <JobStatusLabel job={job} />
          </div>
        )}
        {isDownloaded && <span className={`${styles.badge} ${styles.badgeDownloaded}`}>On NAS</span>}
        {!showActions && !isDownloaded && <JobStatusLabel job={job} />}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// SeriesOverviewTable
// ---------------------------------------------------------------------------

const OVERVIEW_PAGE_SIZE = 20;

function DownloadStatusBadge({ status }: { status: SeriesDownloadStatus }) {
  if (status === "all")
    return <span className={`${styles.badge} ${styles.badgeDownloaded}`}>All downloaded</span>;
  if (status === "partial")
    return <span className={`${styles.badge} ${styles.badgeLoading}`}>Partial</span>;
  if (status === "none")
    return <span className={`${styles.badge} ${styles.badgeMissing}`}>None downloaded</span>;
  return <span className={`${styles.badge} ${styles.badgeUnknown}`}>Unknown</span>;
}

function SeriesOverviewTable({
  onSelect,
}: {
  onSelect: (series: SeriesMeta) => void;
}) {
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<SeriesOverviewRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);

  const load = useCallback(async (q: string, off: number) => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    const data = await fetchSeriesOverview(q, OVERVIEW_PAGE_SIZE, off);
    if (requestId !== requestIdRef.current) return; // stale response, a newer request won the race
    setRows(data.series);
    setTotal(data.total);
    setLoading(false);
  }, []);

  useEffect(() => {
    load(query, offset);
    // Only `offset` should retrigger the effect — query changes go through the
    // debounced handler below, which resets offset to 0 and loads directly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset]);

  const handleQueryChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setQuery(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setOffset(0);
      load(val, 0);
    }, 300);
  };

  const hasPrev = offset > 0;
  const hasNext = offset + OVERVIEW_PAGE_SIZE < total;
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + OVERVIEW_PAGE_SIZE, total);

  return (
    <div className={styles.overviewSection}>
      <h2 className={styles.sectionTitle}>Series overview</h2>
      <input
        type="text"
        className={styles.searchInput}
        placeholder="Filter series by title…"
        value={query}
        onChange={handleQueryChange}
        autoComplete="off"
      />

      {loading ? (
        <p className={styles.episodeEmpty}>Loading…</p>
      ) : rows.length === 0 ? (
        <p className={styles.episodeEmpty}>No series found.</p>
      ) : (
        <>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Title</th>
                <th>JKanime</th>
                <th>Downloads</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr
                  key={s.id}
                  className={styles.overviewRow}
                  onClick={() => onSelect({ id: s.id, title: s.title, slug: "" })}
                >
                  <td>{s.title}</td>
                  <td>
                    {s.jkanimeIngested ? (
                      <span className={`${styles.badge} ${styles.badgeDownloaded}`}>Yes</span>
                    ) : (
                      <span className={`${styles.badge} ${styles.badgeMissing}`}>No</span>
                    )}
                  </td>
                  <td>
                    <DownloadStatusBadge status={s.status} />{" "}
                    <span className={styles.overviewCount}>
                      ({s.downloadedCount}/{s.episodeCount})
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className={styles.pagination}>
            <button
              type="button"
              className={`${styles.triggerBtn} ${styles.triggerBtnSecondary}`}
              onClick={() => setOffset(Math.max(0, offset - OVERVIEW_PAGE_SIZE))}
              disabled={!hasPrev}
            >
              Prev
            </button>
            <span className={styles.paginationLabel}>
              {rangeStart}–{rangeEnd} of {total}
            </span>
            <button
              type="button"
              className={`${styles.triggerBtn} ${styles.triggerBtnSecondary}`}
              onClick={() => setOffset(offset + OVERVIEW_PAGE_SIZE)}
              disabled={!hasNext}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SeriesSearchBox
// ---------------------------------------------------------------------------

function SeriesSearchBox({
  onSelect,
}: {
  onSelect: (s: SeriesMeta) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SeriesMeta[]>([]);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setQuery(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!val.trim()) {
      setResults([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      const data = await fetchSeriesSearch(val);
      setResults(data);
      setOpen(true);
    }, 300);
  };

  const handleSelect = (s: SeriesMeta) => {
    setQuery(s.title);
    setOpen(false);
    setResults([]);
    onSelect(s);
  };

  return (
    <div className={styles.searchSection}>
      <label className={styles.searchLabel} htmlFor="series-search">
        Search series
      </label>
      <input
        id="series-search"
        type="text"
        className={styles.searchInput}
        placeholder="Type a series title…"
        value={query}
        onChange={handleChange}
        onFocus={() => results.length > 0 && setOpen(true)}
        autoComplete="off"
      />
      {open && (
        <ul className={styles.dropdown} role="listbox">
          {results.length === 0 ? (
            <li className={styles.dropdownEmpty}>No series found</li>
          ) : (
            results.map((s) => (
              <li
                key={s.id}
                className={styles.dropdownItem}
                role="option"
                aria-selected={false}
                onMouseDown={() => handleSelect(s)}
              >
                {s.title}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DownloadsManager root
// ---------------------------------------------------------------------------

export function DownloadsManager() {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);

  // One interval per active job, keyed by episode number.
  const intervalsRef = useRef<Map<number, ReturnType<typeof setInterval>>>(new Map());
  // Guard: skip poll tick if a request is already in-flight for this job.
  const inFlightRef = useRef<Set<number>>(new Set());

  // Clear all polling intervals on unmount.
  useEffect(() => {
    return () => {
      for (const id of intervalsRef.current.values()) clearInterval(id);
    };
  }, []);

  const startPolling = useCallback(
    (ep: number, jobId: string) => {
      if (intervalsRef.current.has(ep)) return;

      const id = setInterval(async () => {
        if (inFlightRef.current.has(ep)) return;
        inFlightRef.current.add(ep);
        try {
          const result = await pollJob(jobId);
          dispatch({ type: "JOB_UPDATED", ep, phase: result.status, error: result.error });
          if (result.status === "done" || result.status === "failed") {
            clearInterval(intervalsRef.current.get(ep)!);
            intervalsRef.current.delete(ep);
          }
        } finally {
          inFlightRef.current.delete(ep);
        }
      }, 5000);

      intervalsRef.current.set(ep, id);
    },
    []
  );

  const handleSeriesSelect = useCallback(async (series: SeriesMeta) => {
    // Eagerly dispatch with empty episodes; the status fetch will fill them in.
    dispatch({ type: "SELECT_SERIES", series, episodes: [] });

    const data = await fetchEpisodeStatuses(series.id);
    const episodes: Episode[] = data.episodes.map((e) => ({
      episodeNumber: e.episodeNumber,
      title: e.title,
    }));
    const statuses: Record<number, EpisodeStatus> = {};
    for (const e of data.episodes) {
      statuses[e.episodeNumber] =
        e.status === "downloaded"
          ? "downloaded"
          : e.status === "missing"
          ? "missing"
          : "unknown";
    }

    dispatch({ type: "SELECT_SERIES", series, episodes });
    dispatch({ type: "SET_STATUSES", statuses });
  }, []);

  const handleExpand = useCallback(
    async (ep: number) => {
      if (!state.series) return;
      dispatch({ type: "SOURCES_LOADING", ep });
      const sources = await fetchSources(state.series.id, ep);
      dispatch({ type: "SET_SOURCES", ep, sources });
      if (sources.length > 0) {
        const first = sources.find((s) => s.available);
        if (first) dispatch({ type: "SELECT_SOURCE", ep, source: first.source });
      }
    },
    [state.series]
  );

  const handleSelectSource = useCallback((ep: number, source: string) => {
    dispatch({ type: "SELECT_SOURCE", ep, source });
  }, []);

  const handleTrigger = useCallback(
    async (ep: number) => {
      if (!state.series) return;
      const sources = state.sourcesByEp[ep];
      const available =
        sources && sources !== "loading" ? sources.filter((s) => s.available) : [];
      const source =
        state.selectedSourceByEp[ep] ?? available[0]?.source;
      if (!source) return;

      dispatch({ type: "CLEAR_ERROR" });
      try {
        const result = await triggerDownload(state.series.id, ep, source);
        dispatch({ type: "JOB_STARTED", ep, jobId: result.jobId });
        startPolling(ep, result.jobId);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Download failed";
        if (msg === "no_source") {
          dispatch({ type: "ERROR", message: "No source available for this episode." });
        } else if (msg === "nas_unavailable") {
          dispatch({ type: "ERROR", message: "Download service unavailable." });
        } else {
          dispatch({ type: "ERROR", message: msg });
        }
      }
    },
    [state.series, state.sourcesByEp, state.selectedSourceByEp, startPolling]
  );

  return (
    <div className={styles.root}>
      {state.error && <div className={styles.error}>{state.error}</div>}

      <SeriesOverviewTable onSelect={handleSeriesSelect} />

      <SeriesSearchBox onSelect={handleSeriesSelect} />

      {state.series && (
        <div className={styles.episodeSection}>
          <h2 className={styles.sectionTitle}>{state.series.title}</h2>

          {state.episodes.length === 0 ? (
            <p className={styles.episodeEmpty}>No episodes found for this series.</p>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Title</th>
                  <th>NAS status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {state.episodes.map((ep) => (
                  <EpisodeRow
                    key={ep.episodeNumber}
                    ep={ep}
                    status={state.statusByEp[ep.episodeNumber] ?? "unknown"}
                    sources={state.sourcesByEp[ep.episodeNumber]}
                    selectedSource={state.selectedSourceByEp[ep.episodeNumber]}
                    job={state.jobByEp[ep.episodeNumber]}
                    seriesId={state.series!.id}
                    onExpand={handleExpand}
                    onSelectSource={handleSelectSource}
                    onTrigger={handleTrigger}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

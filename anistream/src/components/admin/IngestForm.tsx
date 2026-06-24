"use client";

import { useState, useEffect, useRef } from "react";
import { ingestSeries, searchSeries, type SeriesResult } from "@/app/actions/ingest";
import AnimeFlvSlugSearch from "@/components/admin/AnimeFlvSlugSearch";
import styles from "@/app/(app)/admin/admin.module.css";

interface IngestResult {
  series_id: string;
  series_title: string;
  episodes_ingested: number;
  kitsu_id: string | null;
  kitsu_episodes_matched: number;
}

export default function IngestForm() {
  const [fallbackSlug, setFallbackSlug] = useState("");
  const [principalSlug, setPrincipalSlug] = useState("");
  const [malId, setMalId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<SeriesResult | null>(null);
  const [candidates, setCandidates] = useState<SeriesResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (selected) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.length < 2) { setCandidates([]); setOpen(false); return; }

    debounceRef.current = setTimeout(async () => {
      const results = await searchSeries(query);
      setCandidates(results);
      setOpen(results.length > 0);
    }, 300);
  }, [query, selected]);

  function handleSelect(item: SeriesResult) {
    setSelected(item);
    setMalId(item.mal_id);
    setQuery(item.title);
    setCandidates([]);
    setOpen(false);
  }

  function handleClear() {
    setSelected(null);
    setMalId(null);
    setQuery("");
    setCandidates([]);
    setOpen(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!malId) return;
    setLoading(true);
    setResult(null);
    setError(null);

    try {
      const data = await ingestSeries(
        malId,
        fallbackSlug.trim() || undefined,
        principalSlug.trim() || undefined
      );
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  const canSubmit = !!malId && (!!fallbackSlug || !!principalSlug) && !loading;

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.field}>
        <label className="label-caps" htmlFor="series-search">
          Series
        </label>
        <div className={styles.combobox}>
          <input
            id="series-search"
            className="input-field"
            type="text"
            placeholder="Search by title…"
            value={query}
            onChange={(e) => { setQuery(e.target.value); if (selected) handleClear(); }}
            onFocus={() => candidates.length > 0 && setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            autoComplete="off"
            disabled={loading}
          />
          {selected && (
            <button type="button" className={styles.clearBtn} onClick={handleClear} disabled={loading}>
              ×
            </button>
          )}
          {open && (
            <ul className={styles.dropdown}>
              {candidates.map((item) => (
                <li
                  key={item.mal_id}
                  className={styles.dropdownItem}
                  onMouseDown={() => handleSelect(item)}
                >
                  <span className={styles.dropdownItemTitle}>{item.title}</span>
                  <span className={styles.dropdownItemMal}>MAL {item.mal_id}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        {selected && (
          <span className={styles.selectedHint}>MAL ID: {selected.mal_id}</span>
        )}
      </div>

      <div className={styles.field}>
        <label className="label-caps">AnimeAV1 slug</label>
        <AnimeFlvSlugSearch
          onSelect={(selectedSlug) => {
            setPrincipalSlug(selectedSlug);
          }}
          disabled={loading}
        />
      </div>

      <div className={styles.field}>
        <label className="label-caps" htmlFor="principal-slug">
          AnimeAV1 slug (principal) <span style={{ fontWeight: 400, textTransform: "none" }}>(opcional)</span>
        </label>
        <input
          id="principal-slug"
          className="input-field"
          type="text"
          placeholder="sono-bisque-doll-wa-koi-wo-suru"
          value={principalSlug}
          onChange={(e) => setPrincipalSlug(e.target.value)}
          disabled={loading}
        />
      </div>

      <div className={styles.field}>
        <label className="label-caps" htmlFor="fallback-slug">
          Fallback Slug (jkanime) <span style={{ fontWeight: 400, textTransform: "none" }}>(opcional)</span>
        </label>
        <input
          id="fallback-slug"
          className="input-field"
          type="text"
          placeholder="jujutsu-kaisen"
          value={fallbackSlug}
          onChange={(e) => setFallbackSlug(e.target.value)}
          disabled={loading}
        />
      </div>

      <button type="submit" className="btn-primary" disabled={!canSubmit}>
        {loading ? "Ingesting…" : "Ingest"}
      </button>

      {error && (
        <div className={styles.error}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && (
        <div className={styles.result}>
          <p className={styles.resultTitle}>{result.series_title}</p>
          <div className={styles.resultStats}>
            <div className={styles.stat}>
              <span className={styles.statValue}>{result.episodes_ingested}</span>
              <span className="label-caps">Episodes ingested</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statValue}>{result.kitsu_episodes_matched}</span>
              <span className="label-caps">Kitsu matched</span>
            </div>
          </div>
        </div>
      )}
    </form>
  );
}

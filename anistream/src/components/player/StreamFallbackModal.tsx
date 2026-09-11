"use client";

import { useState } from "react";
import { saveAnimeav1Source } from "@/app/actions/stream";
import styles from "./stream-fallback.module.css";

interface Props {
  seriesId: string;
  seriesTitle: string;
  episodeTitle: string;
}

interface JkanimeResult {
  title: string;
  slug: string;
  jkanime_url: string;
  thumbnail_url: string | null;
}

export default function StreamFallbackModal({ seriesId, seriesTitle, episodeTitle }: Props) {
  const [query, setQuery] = useState(seriesTitle);
  const [results, setResults] = useState<JkanimeResult[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch() {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    setResults([]);
    setOpen(false);

    try {
      const res = await fetch(
        `/api/series/search-jkanime?q=${encodeURIComponent(query)}&limit=10`,
        { cache: "no-store" }
      );
      if (!res.ok) throw new Error(`Búsqueda falló (${res.status})`);
      const data = (await res.json()) as JkanimeResult[];
      if (data.length === 0) {
        setError("No se encontraron resultados en jkanime");
      } else {
        setResults(data);
        setOpen(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error en la búsqueda");
    } finally {
      setSearching(false);
    }
  }

  async function handleSelect(result: JkanimeResult) {
    setOpen(false);
    setSaving(true);
    setError(null);
    try {
      await saveAnimeav1Source(seriesId, result.slug);
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error saving source");
      setSaving(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      void handleSearch();
    }
  }

  return (
    <div className={styles.wrap}>
      <div className={`card ${styles.cardModal}`}>
        <div className={styles.icon} aria-hidden="true">⚠</div>
        <h2 className={styles.title}>Video no disponible</h2>
        <p className={styles.desc}>
          No se encontró video en AnimeFlv para{" "}
          <strong>{seriesTitle}</strong> — {episodeTitle}.
        </p>
        <p className={styles.desc}>
          Buscá la serie en <strong>jkanime</strong> y seleccioná el resultado
          correcto para usarlo como fuente alternativa.
        </p>

        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.form}>
          <div className={styles.searchRow}>
            <input
              className="input-field"
              type="text"
              placeholder="ej: Re:Zero kara Hajimeru Isekai Seikatsu"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={searching || saving}
              autoFocus
            />
            <button
              className="btn-primary"
              type="button"
              onClick={() => void handleSearch()}
              disabled={searching || saving || !query.trim()}
            >
              {searching ? "Buscando…" : "Buscar"}
            </button>
          </div>

          {open && results.length > 0 && (
            <ul className={styles.results} role="listbox">
              {results.map((result) => (
                <li
                  key={result.slug}
                  role="option"
                  aria-selected={false}
                  className={styles.resultItem}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    void handleSelect(result);
                  }}
                >
                  <span className={styles.resultTitle}>{result.title}</span>
                  <span className={styles.resultSlug}>{result.slug}</span>
                </li>
              ))}
            </ul>
          )}

          {saving && <p className={styles.desc}>Guardando…</p>}
        </div>
      </div>
    </div>
  );
}

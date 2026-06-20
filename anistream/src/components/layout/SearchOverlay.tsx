"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { searchSeries, type SeriesResult } from "@/app/actions/ingest";
import styles from "./Navbar.module.css";

interface SearchOverlayProps {
  onClose: () => void;
}

export function SearchOverlay({ onClose }: SearchOverlayProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SeriesResult[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    debounceRef.current = setTimeout(async () => {
      const res = await searchSeries(query);
      setResults(res);
      setLoading(false);
    }, 300);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (trimmed) {
      router.push(`/search?q=${encodeURIComponent(trimmed)}`);
      onClose();
    }
  }

  const hasQuery = query.trim().length >= 2;

  return (
    <>
      <div className={styles.searchBackdrop} onClick={onClose} aria-hidden="true" />
      <div className={styles.searchOverlay} role="dialog" aria-label="Search anime">
        <form onSubmit={handleSubmit} className={styles.searchForm}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={styles.searchIcon} aria-hidden="true">
            <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
          </svg>
          <input
            ref={inputRef}
            className={styles.searchInput}
            type="search"
            placeholder="Search anime..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
          />
          {query && (
            <button type="button" className={styles.searchClear} onClick={() => setQuery("")} aria-label="Clear">
              ×
            </button>
          )}
        </form>

        {hasQuery && results.length > 0 && (
          <ul className={styles.searchResults}>
            {results.map((r) => (
              <li key={r.id ?? r.mal_id}>
                <Link href={`/series/${r.id}`} className={styles.searchResultItem} onClick={onClose}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  <span className={styles.searchResultTitle}>{r.title}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}

        {hasQuery && results.length > 0 && (
          <div className={styles.searchFooter}>
            <Link
              href={`/search?q=${encodeURIComponent(query.trim())}`}
              className={styles.searchSeeAll}
              onClick={onClose}
            >
              See all results for &ldquo;{query.trim()}&rdquo; &rarr;
            </Link>
          </div>
        )}

        {loading && <p className={styles.searchStatus}>Searching&hellip;</p>}
        {!loading && hasQuery && results.length === 0 && (
          <p className={styles.searchStatus}>No results for &ldquo;{query.trim()}&rdquo;</p>
        )}
      </div>
    </>
  );
}

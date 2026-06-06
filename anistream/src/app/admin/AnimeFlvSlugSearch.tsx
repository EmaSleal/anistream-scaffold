"use client";

import { useState } from "react";
import { searchAnimeFlv, type AnimeFlvResult } from "@/app/actions/ingest";
import styles from "./admin.module.css";

interface Props {
  onSelect: (slug: string, title: string) => void;
  disabled?: boolean;
}

export default function AnimeFlvSlugSearch({ onSelect, disabled = false }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AnimeFlvResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch() {
    if (!query.trim()) {
      setError("Enter a title to search");
      return;
    }

    setLoading(true);
    setError(null);
    setResults([]);

    try {
      console.log("[AnimeFlvSlugSearch] Searching for:", query);
      const res = await searchAnimeFlv(query);
      console.log("[AnimeFlvSlugSearch] Got results:", res.length);

      if (res.length === 0) {
        setError("No results found on AnimeFlv");
      } else {
        setResults(res);
        setOpen(true);
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Search failed";
      console.error("[AnimeFlvSlugSearch] Error:", errMsg);
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  }

  function handleSelect(result: AnimeFlvResult) {
    onSelect(result.slug, result.title);
    setQuery("");
    setResults([]);
    setOpen(false);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      void handleSearch();
    }
  }

  return (
    <div style={{ marginBottom: "1rem" }}>
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          marginBottom: "0.5rem",
        }}
      >
        <input
          type="text"
          placeholder="Search AnimeFlv (e.g., Re:ZERO)…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading || disabled}
          className={styles.input}
          style={{ flex: 1 }}
        />
        <button
          type="button"
          onClick={handleSearch}
          disabled={loading || disabled || !query.trim()}
          style={{
            padding: "0.5rem 1rem",
            background: "var(--color-brand)",
            border: "none",
            borderRadius: "var(--radius-md)",
            color: "#fff",
            fontWeight: 700,
            cursor: loading || disabled || !query.trim() ? "not-allowed" : "pointer",
            opacity: loading || disabled || !query.trim() ? 0.5 : 1,
            fontFamily: "inherit",
            fontSize: "0.9rem",
            whiteSpace: "nowrap",
          }}
        >
          {loading ? "Searching…" : "Search AnimeFlv"}
        </button>
      </div>

      {error && (
        <div
          style={{
            marginBottom: "0.5rem",
            padding: "0.5rem 0.75rem",
            background: "color-mix(in srgb, #ef4444 15%, transparent)",
            border: "1px solid color-mix(in srgb, #ef4444 40%, transparent)",
            borderRadius: "var(--radius-md)",
            fontSize: "0.875rem",
            color: "#fca5a5",
          }}
        >
          {error}
        </div>
      )}

      {open && results.length > 0 && (
        <ul
          className={styles.dropdown}
          style={{
            marginBottom: "0.5rem",
            maxHeight: "250px",
            overflowY: "auto",
          }}
        >
          {results.map((result) => (
            <li
              key={result.slug}
              className={styles.dropdownItem}
              onMouseDown={() => handleSelect(result)}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span className={styles.dropdownItemTitle}>{result.title}</span>
              <span
                style={{
                  fontSize: "0.75rem",
                  color: "var(--color-text-secondary)",
                  fontFamily: "monospace",
                }}
              >
                {result.slug}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

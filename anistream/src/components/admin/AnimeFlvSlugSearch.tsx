"use client";

import { useState } from "react";
import { searchAnimeFlv, type AnimeFlvResult } from "@/app/actions/ingest";

type SearchSource = "animeflv" | "animeav1";

interface AV1Result {
  title: string;
  slug: string;
  thumbnail_url: string;
}

interface Props {
  onSelect: (slug: string, title: string, source?: SearchSource) => void;
  disabled?: boolean;
}

export default function AnimeFlvSlugSearch({ onSelect, disabled = false }: Props) {
  const [source, setSource] = useState<SearchSource>("animeflv");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AnimeFlvResult[] | AV1Result[]>([]);
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
    setOpen(false);

    try {
      if (source === "animeflv") {
        const res = await searchAnimeFlv(query);
        if (res.length === 0) {
          setError("No results found on AnimeFlv");
        } else {
          setResults(res);
          setOpen(true);
        }
      } else {
        const res = await fetch(
          `/api/admin/downloads/search-animeav1?q=${encodeURIComponent(query)}&limit=10`,
          { cache: "no-store" }
        );
        if (!res.ok) throw new Error(`Search failed (${res.status})`);
        const data = (await res.json()) as AV1Result[];
        if (data.length === 0) {
          setError("No results found on AnimeAV1");
        } else {
          setResults(data);
          setOpen(true);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  function handleSelect(result: AnimeFlvResult | AV1Result) {
    onSelect(result.slug, result.title, source);
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

  function switchSource(next: SearchSource) {
    setSource(next);
    setResults([]);
    setOpen(false);
    setError(null);
  }

  const placeholder =
    source === "animeflv"
      ? "Search AnimeFlv (e.g., Re:ZERO)…"
      : "Search AnimeAV1 (e.g., Sono Bisque)…";

  const btnLabel = loading
    ? "Searching…"
    : source === "animeflv"
    ? "Search AnimeFlv"
    : "Search AnimeAV1";

  return (
    <div style={{ marginBottom: "1rem" }}>
      <div
        style={{
          display: "flex",
          marginBottom: "0.5rem",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-md)",
          overflow: "hidden",
          width: "fit-content",
        }}
      >
        {(["animeflv", "animeav1"] as SearchSource[]).map((s) => (
          <button
            key={s}
            type="button"
            disabled={disabled}
            onClick={() => switchSource(s)}
            style={{
              padding: "0.3rem 0.75rem",
              border: "none",
              borderLeft: s === "animeav1" ? "1px solid var(--color-border)" : "none",
              background: source === s ? "var(--color-brand)" : "var(--color-bg-surface)",
              color: source === s ? "#fff" : "var(--color-text-secondary)",
              fontFamily: "inherit",
              fontSize: "0.8rem",
              fontWeight: source === s ? 600 : 400,
              cursor: disabled ? "not-allowed" : "pointer",
            }}
          >
            {s === "animeflv" ? "AnimeFlv" : "AnimeAV1"}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.5rem" }}>
        <input
          type="text"
          placeholder={placeholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading || disabled}
          className="input-field"
          style={{ flex: 1 }}
        />
        <button
          type="button"
          onClick={() => void handleSearch()}
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
          {btnLabel}
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
          style={{
            maxHeight: "250px",
            overflowY: "auto",
            background: "var(--color-bg-primary)",
            border: "1px solid var(--color-border)",
            borderRadius: "0.8rem",
            padding: "0.4rem",
            listStyle: "none",
            margin: "0 0 0.5rem 0",
          }}
        >
          {results.map((result) => (
            <li
              key={result.slug}
              onMouseDown={(e) => {
                e.preventDefault();
                handleSelect(result);
              }}
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "0.25rem",
                padding: "0.7rem 1rem",
                borderRadius: "0.5rem",
                color: "var(--color-text-secondary)",
                cursor: "pointer",
                userSelect: "none",
                transition: "background 150ms, color 150ms",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "rgba(255, 255, 255, 0.06)";
                e.currentTarget.style.color = "var(--color-text-primary)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "var(--color-text-secondary)";
              }}
            >
              <span style={{ fontWeight: 500, fontSize: "0.95rem" }}>{result.title}</span>
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

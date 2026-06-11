"use client";

import { useState, useTransition } from "react";
import { searchJikan } from "@/app/actions/jikan-search";
import { ingestSeries } from "@/app/actions/ingest";
import { checkExistingMalIds } from "@/app/actions/check-mal-ids";
import type { JikanAnime, JikanPagination, JikanSearchParams } from "@/types/jikan";
import styles from "./BrowseTable.module.css";

type IngestRowState = "idle" | "loading" | "done" | "error";

export default function BrowseTable() {
  const [filters, setFilters] = useState<JikanSearchParams>({ page: 1, limit: 25 });
  const [results, setResults] = useState<JikanAnime[]>([]);
  const [pagination, setPagination] = useState<JikanPagination | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const [existingMalIds, setExistingMalIds] = useState<Set<number>>(new Set());

  const [ingestState, setIngestState] = useState<Map<number, IngestRowState>>(new Map());
  const [ingestErrors, setIngestErrors] = useState<Map<number, string>>(new Map());
  const [slugInputs, setSlugInputs] = useState<Map<number, string>>(new Map());

  const [isPending, startTransition] = useTransition();

  function setIngestRowState(malId: number, state: IngestRowState) {
    setIngestState((prev) => new Map(prev).set(malId, state));
  }

  function setIngestRowError(malId: number, msg: string) {
    setIngestErrors((prev) => new Map(prev).set(malId, msg));
  }

  function handleSearch(overrides?: Partial<JikanSearchParams>) {
    const merged = { ...filters, ...overrides };
    setFilters(merged);

    startTransition(async () => {
      setError(null);
      setSearched(true);

      let currentPage = merged.page ?? 1;
      const MAX_AUTO_ADVANCE = 10;

      for (let attempt = 0; attempt < MAX_AUTO_ADVANCE; attempt++) {
        const res = await searchJikan({ ...merged, page: currentPage });

        if ("error" in res) {
          setError(res.error);
          setResults([]);
          setPagination(null);
          setExistingMalIds(new Set());
          return;
        }

        const malIds = res.data.map((a) => a.mal_id);
        const existing = await checkExistingMalIds(malIds);
        const existingSet = new Set(existing);
        const visible = res.data.filter((a) => !existingSet.has(a.mal_id));

        if (visible.length > 0 || !res.pagination.has_next_page) {
          setResults(res.data);
          setPagination(res.pagination);
          setExistingMalIds(existingSet);
          if (currentPage !== merged.page) {
            setFilters((prev) => ({ ...prev, page: currentPage }));
          }
          return;
        }

        currentPage++;
      }

      // Exhausted auto-advance limit without finding new results
      setResults([]);
      setPagination(null);
      setExistingMalIds(new Set());
    });
  }

  function setSlug(malId: number, value: string) {
    setSlugInputs((prev) => new Map(prev).set(malId, value));
  }

  async function handleIngest(malId: number) {
    const slug = slugInputs.get(malId)?.trim();
    if (!slug) return;
    setIngestRowState(malId, "loading");
    try {
      await ingestSeries(slug, malId);
      setIngestRowState(malId, "done");
    } catch (err) {
      setIngestRowState(malId, "error");
      setIngestRowError(
        malId,
        err instanceof Error ? err.message : "Ingest failed"
      );
    }
  }

  function handleFilterChange(
    key: keyof JikanSearchParams,
    value: string
  ) {
    setFilters((prev) => ({
      ...prev,
      [key]: value === "" ? undefined : value,
    }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    handleSearch({ page: 1 });
  }

  return (
    <div style={{ padding: "2rem" }}>
      <h1 style={{ margin: "0 0 1.5rem", fontSize: "1.4rem", fontWeight: 700 }}>
        Browse Catalog
      </h1>

      <form onSubmit={handleSubmit}>
        <div className={styles.filterGrid}>
          <input
            type="text"
            placeholder="Search title (q)"
            value={filters.q ?? ""}
            onChange={(e) => handleFilterChange("q", e.target.value)}
          />

          <select
            value={filters.type ?? ""}
            onChange={(e) => handleFilterChange("type", e.target.value)}
          >
            <option value="">All types</option>
            <option value="tv">TV</option>
            <option value="movie">Movie</option>
            <option value="ova">OVA</option>
            <option value="special">Special</option>
            <option value="ona">ONA</option>
            <option value="music">Music</option>
            <option value="cm">CM</option>
            <option value="pv">PV</option>
            <option value="tv_special">TV Special</option>
          </select>

          <select
            value={filters.status ?? ""}
            onChange={(e) => handleFilterChange("status", e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="airing">Airing</option>
            <option value="complete">Complete</option>
            <option value="upcoming">Upcoming</option>
          </select>

          {/* rating dropdown — rx is intentionally excluded */}
          <select
            value={filters.rating ?? ""}
            onChange={(e) => handleFilterChange("rating", e.target.value)}
          >
            <option value="">All ratings</option>
            <option value="g">G</option>
            <option value="pg">PG</option>
            <option value="pg13">PG-13</option>
            <option value="r17">R17+</option>
            <option value="r">R</option>
          </select>

          <input
            type="number"
            placeholder="Min score (0–10)"
            min={0}
            max={10}
            step={0.1}
            value={filters.min_score ?? ""}
            onChange={(e) => handleFilterChange("min_score", e.target.value)}
          />

          <input
            type="number"
            placeholder="Max score (0–10)"
            min={0}
            max={10}
            step={0.1}
            value={filters.max_score ?? ""}
            onChange={(e) => handleFilterChange("max_score", e.target.value)}
          />

          <select
            value={filters.order_by ?? ""}
            onChange={(e) => handleFilterChange("order_by", e.target.value)}
          >
            <option value="">Order by…</option>
            <option value="score">Score</option>
            <option value="popularity">Popularity</option>
            <option value="title">Title</option>
            <option value="start_date">Start date</option>
            <option value="members">Members</option>
            <option value="rank">Rank</option>
          </select>

          <select
            value={filters.sort ?? ""}
            onChange={(e) => handleFilterChange("sort", e.target.value)}
          >
            <option value="">Sort direction</option>
            <option value="asc">Ascending</option>
            <option value="desc">Descending</option>
          </select>

          <input
            type="text"
            placeholder="Genres (CSV MAL IDs)"
            value={filters.genres ?? ""}
            onChange={(e) => handleFilterChange("genres", e.target.value)}
          />

          <input
            type="text"
            placeholder="Exclude genres (CSV)"
            value={filters.genres_exclude ?? ""}
            onChange={(e) => handleFilterChange("genres_exclude", e.target.value)}
          />

          <input
            type="text"
            placeholder="Start date (YYYY-MM-DD)"
            value={filters.start_date ?? ""}
            onChange={(e) => handleFilterChange("start_date", e.target.value)}
          />

          <input
            type="text"
            placeholder="End date (YYYY-MM-DD)"
            value={filters.end_date ?? ""}
            onChange={(e) => handleFilterChange("end_date", e.target.value)}
          />

          <input
            type="text"
            placeholder="Letter"
            maxLength={1}
            value={filters.letter ?? ""}
            onChange={(e) => handleFilterChange("letter", e.target.value)}
          />

          <select
            value={filters.limit ?? 25}
            onChange={(e) => handleFilterChange("limit", e.target.value)}
          >
            <option value={10}>10 per page</option>
            <option value={25}>25 per page</option>
          </select>

          <div className={styles.filterActions}>
            <button
              type="submit"
              disabled={isPending}
              className={styles.searchBtn}
            >
              {isPending ? "Searching…" : "Search"}
            </button>
          </div>
        </div>
      </form>

      {error && (
        <div className={styles.errorBanner}>{error}</div>
      )}

      <div style={{ overflowX: "auto" }}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Thumbnail</th>
              <th>Title</th>
              <th>Type</th>
              <th>Status</th>
              <th>Score</th>
              <th>Episodes</th>
              <th>MAL ID</th>
              <th>Ingest</th>
            </tr>
          </thead>
          <tbody>
            {results.filter((a) => !existingMalIds.has(a.mal_id)).map((anime) => {
              const rowState = ingestState.get(anime.mal_id) ?? "idle";
              const rowError = ingestErrors.get(anime.mal_id);

              return (
                <tr key={anime.mal_id}>
                  <td>
                    {anime.images?.jpg?.small_image_url ? (
                      <img
                        src={anime.images.jpg.small_image_url}
                        alt={anime.title}
                        className={styles.thumbnail}
                      />
                    ) : (
                      <div className={styles.thumbnailPlaceholder} />
                    )}
                  </td>
                  <td>
                    <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                      {anime.title}
                    </div>
                    {anime.title_english && anime.title_english !== anime.title && (
                      <div style={{ fontSize: "0.78rem", color: "var(--color-text-secondary)" }}>
                        {anime.title_english}
                      </div>
                    )}
                  </td>
                  <td style={{ color: "var(--color-text-secondary)" }}>
                    {anime.type ?? "—"}
                  </td>
                  <td style={{ color: "var(--color-text-secondary)" }}>
                    {anime.status ?? "—"}
                  </td>
                  <td style={{ color: "var(--color-text-secondary)" }}>
                    {anime.score != null ? anime.score.toFixed(1) : "—"}
                  </td>
                  <td style={{ color: "var(--color-text-secondary)" }}>
                    {anime.episodes ?? "—"}
                  </td>
                  <td style={{ color: "var(--color-text-secondary)", fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
                    {anime.mal_id}
                  </td>
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: "4px", alignItems: "flex-start" }}>
                      <input
                        type="text"
                        placeholder="animeflv-slug (required)"
                        value={slugInputs.get(anime.mal_id) ?? ""}
                        onChange={(e) => setSlug(anime.mal_id, e.target.value)}
                        disabled={rowState === "loading" || rowState === "done"}
                        className={styles.slugInput}
                      />
                      <button
                        className={styles.ingestBtn}
                        disabled={rowState === "loading" || rowState === "done" || !slugInputs.get(anime.mal_id)?.trim()}
                        onClick={() => void handleIngest(anime.mal_id)}
                      >
                        {rowState === "loading"
                          ? "Ingesting…"
                          : rowState === "done"
                          ? "Ingested"
                          : "Ingest"}
                      </button>
                      {rowState === "error" && (
                        <span className={styles.statusError}>
                          {rowError ?? "Error"}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}

            {searched && results.length === 0 && !isPending && (
              <tr>
                <td colSpan={8} className={styles.emptyState}>
                  No results found for this search.
                </td>
              </tr>
            )}

            {!searched && (
              <tr>
                <td colSpan={8} className={styles.emptyState}>
                  Use the filters above and click Search to browse the MAL catalog.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {pagination && results.length > 0 && (
        <div className={styles.pagination}>
          <span>
            Page {pagination.current_page} of {pagination.last_visible_page}
          </span>
          <div className={styles.paginationControls}>
            <button
              className={styles.paginationBtn}
              disabled={isPending || (filters.page ?? 1) <= 1}
              onClick={() => handleSearch({ page: (filters.page ?? 1) - 1 })}
            >
              Previous
            </button>
            <button
              className={styles.paginationBtn}
              disabled={isPending || !pagination.has_next_page}
              onClick={() => handleSearch({ page: (filters.page ?? 1) + 1 })}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

"use client";

import { useState, useTransition, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  type SimulcastSeries,
  type SyncResult,
  updateSimulcastSlug,
  syncFromJikan,
} from "@/app/actions/simulcast-admin";
import AnimeFlvSlugSearch from "@/app/admin/AnimeFlvSlugSearch";

interface Props {
  series: SimulcastSeries[];
}

function formatLastCheck(value: string | null): string {
  if (!value) return "Never";
  try {
    return new Date(value).toLocaleDateString("en-CA", { timeZone: "UTC" });
  } catch {
    return value;
  }
}

type SortKey = "title" | "score" | "lastSimulcastCheck";
type SortDirection = "asc" | "desc";

export default function SimulcastTable({ series }: Props) {
  const router = useRouter();
  const [rows, setRows] = useState<SimulcastSeries[]>(series);
  const [editingId, setEditingId] = useState<string | null>(null);
  const cancelledRef = useRef(false);
  const [editValue, setEditValue] = useState<string>("");
  const [slugError, setSlugError] = useState<string | null>(null);

  const [sortKey, setSortKey] = useState<SortKey>("title");
  const [sortDir, setSortDir] = useState<SortDirection>("asc");
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 15;

  const [syncing, startSync] = useTransition();
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  function startEdit(row: SimulcastSeries) {
    setEditingId(row.id);
    setEditValue(row.animeflvSlug ?? "");
    setSlugError(null);
  }

  function cancelEdit() {
    cancelledRef.current = true;
    setEditingId(null);
    setEditValue("");
    setSlugError(null);
  }

  async function handleSave(row: SimulcastSeries) {
    if (cancelledRef.current) {
      cancelledRef.current = false;
      return;
    }
    const trimmed = editValue.trim() || null;
    setEditingId(null);

    // Optimistic update
    const previous = rows;
    setRows((prev) =>
      prev.map((r) => (r.id === row.id ? { ...r, animeflvSlug: trimmed } : r)),
    );

    try {
      await updateSimulcastSlug(row.id, trimmed);
    } catch (err) {
      // Revert on failure
      setRows(previous);
      setSlugError(
        err instanceof Error ? err.message : "Failed to save slug",
      );
    }
  }

  function handleKeyDown(
    e: React.KeyboardEvent<HTMLInputElement>,
    row: SimulcastSeries,
  ) {
    if (e.key === "Enter") {
      e.preventDefault();
      e.currentTarget.blur(); // onBlur → handleSave (single code path, avoids double-save)
    } else if (e.key === "Escape") {
      cancelEdit();
    }
  }

  function handleSync() {
    setSyncResult(null);
    setSyncError(null);

    startSync(async () => {
      try {
        const result = await syncFromJikan();
        setSyncResult(result);
        router.refresh();
      } catch (err) {
        setSyncError(
          err instanceof Error ? err.message : "Sync failed",
        );
      }
    });
  }

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
    setCurrentPage(1);
  }

  const sortedRows = [...rows].sort((a, b) => {
    let aVal: string | number | null;
    let bVal: string | number | null;

    if (sortKey === "title") {
      aVal = a.title.toLowerCase();
      bVal = b.title.toLowerCase();
    } else if (sortKey === "score") {
      aVal = a.score ?? 0;
      bVal = b.score ?? 0;
    } else {
      aVal = a.lastSimulcastCheck ?? "";
      bVal = b.lastSimulcastCheck ?? "";
    }

    const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
    return sortDir === "asc" ? cmp : -cmp;
  });

  const totalPages = Math.ceil(sortedRows.length / itemsPerPage);
  const startIdx = (currentPage - 1) * itemsPerPage;
  const paginatedRows = sortedRows.slice(startIdx, startIdx + itemsPerPage);

  function SortableHeader({ label, sortKeyVal }: { label: string; sortKeyVal: SortKey }) {
    const isActive = sortKey === sortKeyVal;
    const arrow = isActive ? (sortDir === "asc" ? " ↑" : " ↓") : "";
    return (
      <th
        onClick={() => handleSort(sortKeyVal)}
        style={{
          padding: "0.5rem 0.75rem",
          fontWeight: 600,
          cursor: "pointer",
          userSelect: "none",
          color: isActive ? "var(--color-brand)" : "inherit",
          backgroundColor: isActive
            ? "color-mix(in srgb, var(--color-brand) 8%, transparent)"
            : undefined,
        }}
        title="Click to sort"
      >
        {label}
        {arrow}
      </th>
    );
  }

  return (
    <div style={{ padding: "2rem" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "1rem",
        }}
      >
        <h1 style={{ margin: 0, fontSize: "1.4rem", fontWeight: 700 }}>
          Simulcast Manager
        </h1>
        <button
          onClick={handleSync}
          disabled={syncing}
          style={{
            padding: "0.5rem 1rem",
            background: "var(--color-brand)",
            border: "none",
            borderRadius: "var(--radius-md)",
            color: "#fff",
            fontWeight: 700,
            cursor: syncing ? "not-allowed" : "pointer",
            opacity: syncing ? 0.5 : 1,
            fontFamily: "inherit",
            fontSize: "0.9rem",
          }}
        >
          {syncing ? "Syncing…" : "Sync from Jikan"}
        </button>
      </div>

      {slugError && (
        <div
          style={{
            marginBottom: "1rem",
            padding: "0.75rem",
            background: "color-mix(in srgb, #ef4444 15%, transparent)",
            border: "1px solid color-mix(in srgb, #ef4444 40%, transparent)",
            borderRadius: "var(--radius-md)",
            fontSize: "0.875rem",
            color: "#fca5a5",
          }}
        >
          {slugError}
        </div>
      )}

      {syncResult && (
        <div
          style={{
            marginBottom: "1rem",
            padding: "0.75rem",
            background: "color-mix(in srgb, #22c55e 15%, transparent)",
            border: "1px solid color-mix(in srgb, #22c55e 40%, transparent)",
            borderRadius: "var(--radius-md)",
            fontSize: "0.875rem",
            color: "#86efac",
          }}
        >
          Sync complete — Added {syncResult.added}, Updated {syncResult.updated}, Skipped{" "}
          {syncResult.skipped}
        </div>
      )}

      {syncError && (
        <div
          style={{
            marginBottom: "1rem",
            padding: "0.75rem",
            background: "color-mix(in srgb, #ef4444 15%, transparent)",
            border: "1px solid color-mix(in srgb, #ef4444 40%, transparent)",
            borderRadius: "var(--radius-md)",
            fontSize: "0.875rem",
            color: "#fca5a5",
          }}
        >
          Sync error: {syncError}
        </div>
      )}

      <div style={{ overflowX: "auto" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "0.9rem",
          }}
        >
          <thead>
            <tr
              style={{
                borderBottom: "1px solid var(--color-border-base)",
                textAlign: "left",
              }}
            >
              <SortableHeader label="Title" sortKeyVal="title" />
              <th style={{ padding: "0.5rem 0.75rem", fontWeight: 600 }}>AnimeFlv Slug</th>
              <th style={{ padding: "0.5rem 0.75rem", fontWeight: 600 }}>MAL ID</th>
              <SortableHeader label="Score" sortKeyVal="score" />
              <SortableHeader label="Last Check" sortKeyVal="lastSimulcastCheck" />
            </tr>
          </thead>
          <tbody>
            {paginatedRows.map((row) => (
              <tr
                key={row.id}
                style={{ borderBottom: "1px solid var(--color-border-base)" }}
              >
                <td style={{ padding: "0.5rem 0.75rem" }}>{row.title}</td>
                <td style={{ padding: "0.5rem 0.75rem" }}>
                  {editingId === row.id ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                      <div onMouseDown={(e) => e.preventDefault()}>
                        <AnimeFlvSlugSearch
                          onSelect={(slug) => setEditValue(slug)}
                          disabled={false}
                        />
                      </div>
                      <input
                        autoFocus
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, row)}
                        onBlur={() => void handleSave(row)}
                        style={{
                          padding: "0.25rem 0.5rem",
                          background: "var(--color-bg-surface)",
                          border: "1px solid var(--color-brand)",
                          borderRadius: "var(--radius-md)",
                          color: "var(--color-text-primary)",
                          fontSize: "0.875rem",
                          fontFamily: "inherit",
                          width: "100%",
                          outline: "none",
                        }}
                      />
                    </div>
                  ) : (
                    <span
                      onClick={() => startEdit(row)}
                      style={{
                        cursor: "pointer",
                        color: row.animeflvSlug
                          ? "var(--color-text-primary)"
                          : "var(--color-text-secondary)",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.4rem",
                      }}
                      title="Click to edit"
                    >
                      {row.animeflvSlug ?? "—"}
                      <span style={{ fontSize: "0.75rem", opacity: 0.6 }}>✎</span>
                    </span>
                  )}
                </td>
                <td style={{ padding: "0.5rem 0.75rem", color: "var(--color-text-secondary)" }}>
                  {row.malId ?? "—"}
                </td>
                <td style={{ padding: "0.5rem 0.75rem", color: "var(--color-text-secondary)" }}>
                  {row.score ? row.score.toFixed(1) : "—"}
                </td>
                <td style={{ padding: "0.5rem 0.75rem", color: "var(--color-text-secondary)" }}>
                  {formatLastCheck(row.lastSimulcastCheck)}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  style={{
                    padding: "2rem",
                    textAlign: "center",
                    color: "var(--color-text-secondary)",
                  }}
                >
                  No simulcast series found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {rows.length > 0 && (
        <div
          style={{
            marginTop: "1.5rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontSize: "0.875rem",
            color: "var(--color-text-secondary)",
          }}
        >
          <span>
            Showing {Math.min(startIdx + 1, sortedRows.length)}–{Math.min(
              startIdx + itemsPerPage,
              sortedRows.length,
            )}{" "}
            of {sortedRows.length}
          </span>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
              style={{
                padding: "0.4rem 0.8rem",
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                color: "var(--color-text-primary)",
                cursor: currentPage === 1 ? "not-allowed" : "pointer",
                opacity: currentPage === 1 ? 0.5 : 1,
                fontFamily: "inherit",
                fontSize: "0.875rem",
              }}
            >
              Previous
            </button>
            <span style={{ padding: "0.4rem 0.8rem" }}>
              Page {currentPage} of {totalPages || 1}
            </span>
            <button
              onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
              style={{
                padding: "0.4rem 0.8rem",
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                color: "var(--color-text-primary)",
                cursor: currentPage === totalPages ? "not-allowed" : "pointer",
                opacity: currentPage === totalPages ? 0.5 : 1,
                fontFamily: "inherit",
                fontSize: "0.875rem",
              }}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

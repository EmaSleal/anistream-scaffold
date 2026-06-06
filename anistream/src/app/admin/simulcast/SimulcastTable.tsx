"use client";

import { useState, useTransition, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  type SimulcastSeries,
  type SyncResult,
  updateSimulcastSlug,
  syncFromJikan,
} from "@/app/actions/simulcast-admin";

interface Props {
  series: SimulcastSeries[];
}

function formatLastCheck(value: string | null): string {
  if (!value) return "Never";
  try {
    return new Date(value).toLocaleDateString();
  } catch {
    return value;
  }
}

export default function SimulcastTable({ series }: Props) {
  const router = useRouter();
  const [rows, setRows] = useState<SimulcastSeries[]>(series);
  const [editingId, setEditingId] = useState<string | null>(null);
  const cancelledRef = useRef(false);
  const [editValue, setEditValue] = useState<string>("");
  const [slugError, setSlugError] = useState<string | null>(null);

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
              <th style={{ padding: "0.5rem 0.75rem", fontWeight: 600 }}>Title</th>
              <th style={{ padding: "0.5rem 0.75rem", fontWeight: 600 }}>AnimeFlv Slug</th>
              <th style={{ padding: "0.5rem 0.75rem", fontWeight: 600 }}>MAL ID</th>
              <th style={{ padding: "0.5rem 0.75rem", fontWeight: 600 }}>Last Check</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                style={{ borderBottom: "1px solid var(--color-border-base)" }}
              >
                <td style={{ padding: "0.5rem 0.75rem" }}>{row.title}</td>
                <td style={{ padding: "0.5rem 0.75rem" }}>
                  {editingId === row.id ? (
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
                  {formatLastCheck(row.lastSimulcastCheck)}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={4}
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
    </div>
  );
}

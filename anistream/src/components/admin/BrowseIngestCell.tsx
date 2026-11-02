"use client";

import { useState } from "react";
import { useFranchiseIngest } from "@/hooks/useFranchiseIngest";
import AnimeFlvSlugSearch from "@/components/admin/AnimeFlvSlugSearch";
import FranchiseIngestProgress from "@/components/admin/FranchiseIngestProgress";
import styles from "./BrowseTable.module.css";

/** Per-row ingest control: main ingest, then each franchise member (ADR-015). */
export default function BrowseIngestCell({ malId }: { malId: number }) {
  const franchise = useFranchiseIngest();
  const [slug, setSlug] = useState("");
  const [started, setStarted] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const busy = franchise.running || (started && !done && !error);

  async function handleIngest() {
    const trimmed = slug.trim();
    if (!trimmed) return;
    setStarted(true);
    setDone(false);
    setError(null);
    try {
      await franchise.start(malId, undefined, trimmed);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ingest failed");
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "4px", alignItems: "flex-start" }}>
      <AnimeFlvSlugSearch onSelect={setSlug} disabled={busy || done} />
      {slug && <span className={styles.slugLabel}>{slug}</span>}
      <button
        className={styles.ingestBtn}
        disabled={busy || done || !slug.trim()}
        onClick={() => void handleIngest()}
      >
        {busy ? "Ingesting…" : done ? "Ingested" : "Ingest"}
      </button>
      {error && <span className={styles.statusError}>{error}</span>}
      <FranchiseIngestProgress controller={franchise} />
    </div>
  );
}

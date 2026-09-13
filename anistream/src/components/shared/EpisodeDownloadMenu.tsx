"use client";

import { useEffect, useRef, useState } from "react";
import { fetchSources, triggerDownload, pollJob, type JobPhase } from "@/lib/downloads-client";
import styles from "./EpisodeDownloadMenu.module.css";

interface EpisodeDownloadMenuProps {
  seriesId: string;
  episodeNumber: number;
}

type MenuState =
  | { phase: "idle" }
  | { phase: "checking" }
  | { phase: "no-source" }
  | { phase: "job"; jobPhase: JobPhase; error?: string };

export function EpisodeDownloadMenu({ seriesId, episodeNumber }: EpisodeDownloadMenuProps) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<MenuState>({ phase: "idle" });
  const containerRef = useRef<HTMLDivElement>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!open) return;
    function onOutsideClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, [open]);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  function handleToggle(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setOpen((v) => !v);
  }

  async function handleDownload(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setState({ phase: "checking" });
    const sources = await fetchSources(seriesId, episodeNumber);
    const available = sources.find((s) => s.available);
    if (!available) {
      setState({ phase: "no-source" });
      return;
    }
    try {
      const result = await triggerDownload(seriesId, episodeNumber, available.source);
      setState({ phase: "job", jobPhase: result.status });
      intervalRef.current = setInterval(async () => {
        const poll = await pollJob(result.jobId);
        setState({ phase: "job", jobPhase: poll.status, error: poll.error });
        if (poll.status === "done" || poll.status === "failed") {
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
      }, 5000);
    } catch (err) {
      setState({
        phase: "job",
        jobPhase: "failed",
        error: err instanceof Error ? err.message : "Download failed",
      });
    }
  }

  function stopClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
  }

  return (
    <div ref={containerRef} className={styles.wrap} onClick={stopClick}>
      <button
        className={styles.menuBtn}
        aria-label="Opciones de episodio"
        aria-expanded={open}
        onClick={handleToggle}
      >
        ⋮
      </button>
      {open && (
        <div className={styles.menuDropdown}>
          {state.phase === "idle" && (
            <button className={styles.menuItem} onMouseDown={handleDownload}>
              Descargar
            </button>
          )}
          {state.phase === "checking" && (
            <span className={styles.menuItemStatic}>Buscando fuente…</span>
          )}
          {state.phase === "no-source" && (
            <span className={styles.menuItemStatic}>Sin fuente disponible</span>
          )}
          {state.phase === "job" && (
            <span className={styles.menuItemStatic}>
              {state.jobPhase === "pending" && "En cola…"}
              {state.jobPhase === "downloading" && "Descargando…"}
              {state.jobPhase === "done" && "Descargado ✓"}
              {state.jobPhase === "failed" && `Error: ${state.error ?? "desconocido"}`}
              {state.jobPhase === "unknown" && "Estado desconocido"}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

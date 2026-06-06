"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ingestSeries } from "@/app/actions/ingest";
import { saveAnimeav1Source } from "@/app/actions/stream";
import AnimeFlvSlugSearch from "@/app/admin/AnimeFlvSlugSearch";
import styles from "./ingest-trigger.module.css";

type Phase = "loading" | "success" | "failed";

interface Props {
  seriesId: string;
  malId: number;
  animeflvSlug: string | null;
}

export default function IngestTrigger({ seriesId, malId, animeflvSlug }: Props) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("loading");
  const [animeflvCustom, setAnimeflvCustom] = useState("");
  const [animeav1Custom, setAnimeav1Custom] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [animeflvStatus, setAnimeflvStatus] = useState<"unknown" | "ok" | "failed">("unknown");

  async function tryIngest(slug: string) {
    try {
      await ingestSeries(slug, malId);
      setAnimeflvStatus("ok");
      setPhase("success");
      router.refresh();
    } catch (err) {
      setAnimeflvStatus("failed");
      setErrorMsg(err instanceof Error ? err.message : "Ingest failed");
      setPhase("failed");
    }
  }

  useEffect(() => {
    tryIngest(animeflvSlug ?? seriesId);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleRetry(e: React.FormEvent) {
    e.preventDefault();
    setRetrying(true);
    setErrorMsg(null);

    const flvSlug = animeflvCustom.trim();
    const av1Slug = animeav1Custom.trim();

    // Save animeav1 slug if provided (independent of animeflv result)
    if (av1Slug) {
      try {
        await saveAnimeav1Source(seriesId, av1Slug);
      } catch {
        // Non-blocking — animeflv ingest might still work
      }
    }

    if (flvSlug) {
      await tryIngest(flvSlug);
    }

    setRetrying(false);
  }

  if (phase === "loading") {
    return (
      <div className={styles.status}>
        <span className={styles.spinner} />
        Buscando episodios…
      </div>
    );
  }

  if (phase === "success") {
    return (
      <div className={styles.status}>
        Episodios encontrados. Actualizando…
      </div>
    );
  }

  return (
    <>
      <div className={styles.status} style={{ color: "rgba(255,255,255,0.4)" }}>
        No hay episodios disponibles.
      </div>
      <div className={styles.backdrop}>
        <div className={styles.modal}>
          <h2 className={styles.modalTitle}>No se encontraron episodios</h2>

          <div className={styles.statusRow}>
            <span className={`${styles.statusDot} ${styles.statusFailed}`} />
            <span className={styles.statusLabel}>
              AnimeFlv: <code className={styles.code}>{animeflvSlug ?? seriesId}</code> — no encontrado
            </span>
          </div>

          {errorMsg && <p className={styles.modalError}>{errorMsg}</p>}

          <form onSubmit={handleRetry} className={styles.modalForm}>
            <div className={styles.modalFieldGroup}>
              <label className={styles.modalLabel}>
                AnimeFlv slug <span className={styles.required}>*</span>
              </label>
              <AnimeFlvSlugSearch
                onSelect={(slug) => setAnimeflvCustom(slug)}
                disabled={retrying}
              />
              <input
                className={styles.modalInput}
                type="text"
                placeholder="ej: jujutsu-kaisen-tv"
                value={animeflvCustom}
                onChange={(e) => setAnimeflvCustom(e.target.value)}
                required
                disabled={retrying}
                autoFocus
              />
            </div>

            <div className={styles.modalFieldGroup}>
              <label className={styles.modalLabel}>
                AnimeAV1 slug <span className={styles.optional}>(opcional — fuente de video alternativa)</span>
              </label>
              <input
                className={styles.modalInput}
                type="text"
                placeholder="ej: jujutsu-kaisen"
                value={animeav1Custom}
                onChange={(e) => setAnimeav1Custom(e.target.value)}
                disabled={retrying}
              />
            </div>

            <button
              className={styles.modalBtn}
              type="submit"
              disabled={retrying || !animeflvCustom.trim()}
            >
              {retrying ? "Reintentando…" : "Reintentar ingest"}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}

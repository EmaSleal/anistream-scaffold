"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ingestSeries } from "@/app/actions/ingest";
import AnimeFlvSlugSearch from "@/components/admin/AnimeFlvSlugSearch";
import styles from "./ingest-trigger.module.css";

type Phase = "loading" | "success" | "failed";

interface Props {
  seriesId: string;
  malId: number;
}

export default function IngestTrigger({ seriesId, malId }: Props) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("loading");
  const [animeav1Custom, setAnimeav1Custom] = useState("");
  const [fallbackCustom, setFallbackCustom] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function tryIngest(fallbackSlug?: string, animeav1Slug?: string) {
    try {
      const result = await ingestSeries(malId, fallbackSlug, animeav1Slug);
      if (result.episodes_ingested > 0) {
        setPhase("success");
        router.refresh();
      } else {
        // No real video source resolved (e.g. the AnimeAV1 slug guess didn't
        // match) — surface the retry form instead of masking it as success.
        setPhase("failed");
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Ingest failed");
      setPhase("failed");
    }
  }

  useEffect(() => {
    // Guess: the series' own canonical slug is often also its AnimeAV1 slug.
    // If AnimeAV1 doesn't have it, ingest returns 0 real episodes and the
    // retry form below lets an admin supply the correct slug.
    tryIngest(undefined, seriesId);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleRetry(e: React.FormEvent) {
    e.preventDefault();
    setRetrying(true);
    setErrorMsg(null);
    await tryIngest(fallbackCustom.trim() || undefined, animeav1Custom.trim() || undefined);
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
        <div className={`card ${styles.modalCard}`}>
          <h2 className={styles.modalTitle}>No se encontraron episodios</h2>

          <div className={styles.statusRow}>
            <span className={`${styles.statusDot} ${styles.statusFailed}`} />
            <span className={styles.statusLabel}>
              AnimeAV1: <code className={styles.code}>{seriesId}</code> — no encontrado
            </span>
          </div>

          {errorMsg && <p className={styles.modalError}>{errorMsg}</p>}

          <form onSubmit={handleRetry} className={styles.modalForm}>
            <div className={styles.modalFieldGroup}>
              <label className="label-caps">
                AnimeAV1 slug <span className={styles.optional}>(opcional — fuente principal de video)</span>
              </label>
              <AnimeFlvSlugSearch
                onSelect={(slug) => setAnimeav1Custom(slug)}
                disabled={retrying}
              />
              <input
                className="input-field"
                type="text"
                placeholder="ej: jujutsu-kaisen-tv"
                value={animeav1Custom}
                onChange={(e) => setAnimeav1Custom(e.target.value)}
                disabled={retrying}
                autoFocus
              />
            </div>

            <div className={styles.modalFieldGroup}>
              <label className="label-caps">
                Fallback Slug (jkanime) <span className={styles.optional}>(opcional — fuente de video alternativa)</span>
              </label>
              <input
                className="input-field"
                type="text"
                placeholder="ej: jujutsu-kaisen"
                value={fallbackCustom}
                onChange={(e) => setFallbackCustom(e.target.value)}
                disabled={retrying}
              />
            </div>

            <button
              className="btn-primary"
              type="submit"
              disabled={retrying || (!animeav1Custom.trim() && !fallbackCustom.trim())}
            >
              {retrying ? "Reintentando…" : "Reintentar ingest"}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}

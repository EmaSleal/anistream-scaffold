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
  animeflvSlug: string | null;
}

export default function IngestTrigger({ seriesId, malId, animeflvSlug }: Props) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("loading");
  const [animeflvCustom, setAnimeflvCustom] = useState("");
  const [fallbackCustom, setFallbackCustom] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function tryIngest(flvSlug: string | undefined, av1Slug?: string) {
    try {
      await ingestSeries(flvSlug, malId, av1Slug);
      setPhase("success");
      router.refresh();
    } catch (err) {
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
    await tryIngest(animeflvCustom.trim() || undefined, fallbackCustom.trim() || undefined);
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
              AnimeFlv: <code className={styles.code}>{animeflvSlug ?? seriesId}</code> — no encontrado
            </span>
          </div>

          {errorMsg && <p className={styles.modalError}>{errorMsg}</p>}

          <form onSubmit={handleRetry} className={styles.modalForm}>
            <div className={styles.modalFieldGroup}>
              <label className="label-caps">
                AnimeFlv slug <span className={styles.optional}>(opcional — fuente de episodios)</span>
              </label>
              <AnimeFlvSlugSearch
                onSelect={(slug) => setAnimeflvCustom(slug)}
                disabled={retrying}
              />
              <input
                className="input-field"
                type="text"
                placeholder="ej: jujutsu-kaisen-tv"
                value={animeflvCustom}
                onChange={(e) => setAnimeflvCustom(e.target.value)}
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
              disabled={retrying || (!animeflvCustom.trim() && !fallbackCustom.trim())}
            >
              {retrying ? "Reintentando…" : "Reintentar ingest"}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}

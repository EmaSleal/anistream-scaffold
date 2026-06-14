"use client";

import { useState } from "react";
import { saveAnimeav1Source } from "@/app/actions/stream";
import styles from "./stream-fallback.module.css";

interface Props {
  seriesId: string;
  seriesTitle: string;
  episodeTitle: string;
}

export default function StreamFallbackModal({ seriesId, seriesTitle, episodeTitle }: Props) {
  const [slug, setSlug] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = slug.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      await saveAnimeav1Source(seriesId, trimmed);
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error saving source");
      setLoading(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <div className={`card ${styles.cardModal}`}>
        <div className={styles.icon} aria-hidden="true">⚠</div>
        <h2 className={styles.title}>Video no disponible</h2>
        <p className={styles.desc}>
          No se encontró video en AnimeFlv para{" "}
          <strong>{seriesTitle}</strong> — {episodeTitle}.
        </p>
        <p className={styles.desc}>
          Ingresá el slug de <strong>jkanime</strong> para esta serie y lo
          usaremos como fuente alternativa.
        </p>

        {error && <p className={styles.error}>{error}</p>}

        <form onSubmit={handleSubmit} className={styles.form}>
          <input
            className="input-field"
            type="text"
            placeholder="ej: jujutsu-kaisen"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            disabled={loading}
            autoFocus
            required
          />
          <button className="btn-primary" type="submit" disabled={loading || !slug.trim()}>
            {loading ? "Guardando…" : "Guardar y reproducir"}
          </button>
        </form>
      </div>
    </div>
  );
}

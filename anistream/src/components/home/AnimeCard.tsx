"use client";

import Link from "next/link";
import Image from "next/image";
import type { Series } from "@/types";
import styles from "./AnimeCard.module.css";

interface AnimeCardProps {
  series: Series;
}

export function AnimeCard({ series }: AnimeCardProps) {
  const formatLabel = series.audioFormats
    .map((f) => f.charAt(0).toUpperCase() + f.slice(1))
    .join(" | ");

  return (
    <Link href={`/series/${series.id}`} className={styles.card}>
      <div className={styles.thumb}>
        <Image
          src={series.thumbnailUrl}
          alt={series.title}
          fill
          sizes="(max-width: 768px) 140px, 160px"
          className={styles.image}
          placeholder="blur"
          blurDataURL="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        />
        <div className={styles.overlay} aria-hidden="true" />
      </div>
      <div className={styles.body}>
        <p className={styles.title}>{series.title}</p>
        <div className={styles.meta}>
          <span className={styles.format}>{formatLabel}</span>
          <button
            className={styles.menuBtn}
            aria-label={`More options for ${series.title}`}
            onClick={(e) => e.preventDefault()}
          >
            ···
          </button>
        </div>
      </div>
    </Link>
  );
}

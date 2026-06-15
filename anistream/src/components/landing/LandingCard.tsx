import Link from "next/link";
import Image from "next/image";
import type { Series } from "@/types";
import styles from "./LandingCard.module.css";

interface LandingCardProps {
  series: Series;
}

export function LandingCard({ series }: LandingCardProps) {
  return (
    <Link href={`/series/${series.id}`} className={styles.card}>
      <div className={styles.thumb}>
        <Image
          src={series.thumbnailUrl}
          alt={series.title}
          fill
          sizes="(max-width: 768px) 120px, 140px"
          className={styles.image}
          placeholder="blur"
          blurDataURL="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        />
        <div className={styles.overlay} aria-hidden="true" />
      </div>
      <p className={styles.title}>{series.title}</p>
    </Link>
  );
}

import Image from "next/image";
import Link from "next/link";
import type { Series } from "@/types";
import { Badge } from "@/components/ui/Badge";
import { SeriesDetailsToggle } from "./SeriesDetailsToggle";
import styles from "./SeriesBanner.module.css";

interface SeriesBannerProps {
  series: Series;
}

function Stars({ score }: { score?: number }) {
  const filled = score ? Math.round(score / 2) : 0;
  return (
    <div className={styles.stars} aria-label={`Rating: ${score ?? "N/A"} out of 10`}>
      {Array.from({ length: 5 }, (_, i) => (
        <svg key={i} width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"
          fill={i < filled ? "#F47521" : "none"} stroke="#F47521" strokeWidth="2">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
        </svg>
      ))}
      {score && <span className={styles.scoreText}>{score.toFixed(1)}</span>}
    </div>
  );
}

export function SeriesBanner({ series }: SeriesBannerProps) {
  const tags = [
    series.rating,
    "HD",
    ...series.genres.slice(0, 4),
  ];

  const audioLanguages = "Japanese, Español (América Latina), English, Deutsch, Français";

  return (
    <section className={styles.banner} aria-label={series.title}>
      <div className={styles.backdrop}>
        <Image
          src={series.bannerUrl || series.thumbnailUrl}
          alt=""
          fill
          priority
          sizes="100vw"
          className={styles.backdropImg}
        />
        <div className={styles.gradientLeft} />
        <div className={styles.gradientBottom} />
      </div>

      <div className={styles.content}>
        <div className={styles.left}>
          <div className={styles.titleWrap}>
            <Image
              src={series.thumbnailUrl}
              alt={series.title}
              width={120}
              height={170}
              className={styles.poster}
            />
            <div className={styles.titleInfo}>
              <h1 className={styles.title}>{series.title}</h1>
              <Stars score={series.score} />
              <div className={styles.tags}>
                {tags.map((tag) => (
                  <span key={tag} className={styles.tag}>{tag}</span>
                ))}
              </div>
            </div>
          </div>

          <div className={styles.actions}>
            <Link href={`/watch/ptmm-e5`} className={styles.playBtn}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              EMPEZAR A VER E1
            </Link>
            <button className={styles.iconBtn} aria-label="Add to watchlist">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z" />
              </svg>
            </button>
            <button className={styles.iconBtn} aria-label="Share">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
              </svg>
            </button>
          </div>

          <SeriesDetailsToggle series={series} audioLanguages={audioLanguages} />
        </div>

        <div className={styles.right}>
          <div className={styles.audioPanel}>
            <p className={styles.audioPanelLabel}>Audio</p>
            <p className={styles.audioPanelValue}>{audioLanguages}</p>
          </div>
        </div>
      </div>
    </section>
  );
}

import type { ReactNode } from "react";
import styles from "./FeatureGrid.module.css";

interface Feature {
  icon: ReactNode;
  title: string;
  subtitle: string;
}

const FEATURES: Feature[] = [
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="2" y="3" width="20" height="14" rx="2" />
        <path d="M8 21h8M12 17v4" />
        <path d="m10 9 5 3-5 3V9z" fill="currentColor" stroke="none" />
      </svg>
    ),
    title: "Massive Library",
    subtitle: "Thousands of titles, classic to simulcast",
  },
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 6v6l4 2" />
      </svg>
    ),
    title: "Day-0 Simulcasts",
    subtitle: "Watch within hours of Japan broadcast",
  },
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8" />
      </svg>
    ),
    title: "Sub & Dub",
    subtitle: "Choose your preferred audio track",
  },
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
    title: "Free Forever",
    subtitle: "No subscription. No credit card.",
  },
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="5" y="2" width="14" height="20" rx="2" />
        <path d="M12 18h.01" />
      </svg>
    ),
    title: "Mobile Ready",
    subtitle: "Stream on any device, anywhere",
  },
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z" />
      </svg>
    ),
    title: "Watchlist & Progress",
    subtitle: "Pick up right where you left off",
  },
];

export function FeatureGrid() {
  return (
    <section id="features" className={styles.section}>
      <div className={styles.container}>
        <h2 className={styles.heading}>Everything you need to watch anime</h2>
        <p className={styles.subheading}>No ads. No fees. Just anime.</p>
        <div className={styles.grid}>
          {FEATURES.map((feature) => (
            <article key={feature.title} className={styles.card}>
              <div className={styles.iconWrap} aria-hidden="true">
                {feature.icon}
              </div>
              <h3 className={styles.cardTitle}>{feature.title}</h3>
              <p className={styles.cardSubtitle}>{feature.subtitle}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

export const dynamic = "force-dynamic";

import Link from "next/link";
import AllAnimeTab from "@/components/browse/AllAnimeTab";
import SimulcastsTab from "@/components/browse/SimulcastsTab";
import GenresTab from "@/components/browse/GenresTab";
import type { Metadata } from "next";
import styles from "./browse.module.css";

export const metadata: Metadata = { title: "Browse", robots: { index: false, follow: false } };

const TABS = [
  { label: "All Anime",    key: "all",        href: "/browse" },
  { label: "Simulcasts",   key: "simulcasts", href: "/browse?tab=simulcasts" },
  { label: "Anime Genres", key: "genres",     href: "/browse?tab=genres" },
] as const;

type Tab = "all" | "simulcasts" | "genres";

export default async function BrowsePage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string; genre?: string; year?: string; season?: string }>;
}) {
  const { tab: tabParam, genre, year, season } = await searchParams;
  const activeTab: Tab =
    tabParam === "simulcasts" ? "simulcasts"
    : tabParam === "genres" ? "genres"
    : "all";

  return (
    <div className="page-content">
      <nav className={styles.tabs} aria-label="Browse filters">
        {TABS.map((t) => (
          <Link
            key={t.key}
            href={t.href}
            className={`${styles.tab} ${activeTab === t.key ? styles.tabActive : ""}`}
            aria-current={activeTab === t.key ? "page" : undefined}
          >
            {t.label}
          </Link>
        ))}
      </nav>

      {activeTab === "all"        && <AllAnimeTab />}
      {activeTab === "simulcasts" && <SimulcastsTab />}
      {activeTab === "genres"     && <GenresTab genre={genre} year={year} season={season} />}
    </div>
  );
}

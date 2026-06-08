export const dynamic = "force-dynamic";

import Link from "next/link";
import { AnimeCard } from "@/components/home/AnimeCard";
import { SeriesRow } from "@/components/home/SeriesRow";
import { getSeriesList, getSimulcastSeries, getDiscoverSeries, consolidateFranchises } from "@/lib/series";
import type { SeriesListParams } from "@/lib/series";
import { topGenres } from "@/lib/genres";
import { FilterBar } from "./FilterBar";
import type { Metadata } from "next";
import type { Series } from "@/types";
import styles from "./browse.module.css";

export const metadata: Metadata = { title: "Browse" };

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

async function AllAnimeTab() {
  const series = await getSeriesList(50);
  return (
    <>
      <div className={styles.header}>
        <h1 className={styles.heading}>Popular</h1>
      </div>
      <div className={styles.grid} role="list">
        {series.map((s) => (
          <div key={s.id} role="listitem">
            <AnimeCard series={s} />
          </div>
        ))}
      </div>
    </>
  );
}

async function SimulcastsTab() {
  const series = await getSimulcastSeries(100);
  const consolidated = consolidateFranchises(series);
  const genres = topGenres(consolidated, 8);

  if (consolidated.length === 0) {
    return (
      <p style={{ color: "var(--color-text-secondary)", fontSize: "1.6rem" }}>
        No simulcast series available right now. Check back soon.
      </p>
    );
  }

  return (
    <div>
      {genres.map((genre) => {
        const genreSeries = consolidated
          .filter((s: Series) => s.genres?.includes(genre as never))
          .slice(0, 10);
        if (genreSeries.length === 0) return null;
        return <SeriesRow key={genre} title={genre} series={genreSeries} />;
      })}
    </div>
  );
}

interface GenresTabProps {
  genre?: string;
  year?: string;
  season?: string;
}

async function GenresTab({ genre, year, season }: GenresTabProps) {
  const hasFilter = Boolean(genre || year || season);

  let consolidated: Series[];
  if (hasFilter) {
    const params: SeriesListParams = {
      limit: 100,
      genre,
      year: year ? Number(year) : undefined,
      season,
    };
    const series = await getSeriesList(params);
    consolidated = consolidateFranchises(series);
  } else {
    const series = await getDiscoverSeries();
    const raw = consolidateFranchises(series);
    consolidated = [...raw].sort(() => Math.random() - 0.5);
  }

  const genres = topGenres(consolidated, 12);

  return (
    <>
      <FilterBar
        title="Discover"
        genres={genres}
        activeGenre={genre}
        activeYear={year}
        activeSeason={season}
      />
      {hasFilter && consolidated.length === 0 ? (
        <p style={{ color: "var(--color-text-secondary)", fontSize: "1.6rem" }}>
          No series match these filters.
        </p>
      ) : (
        <div className={styles.grid} role="list">
          {consolidated.map((s) => (
            <div key={s.id} role="listitem">
              <AnimeCard series={s} />
            </div>
          ))}
        </div>
      )}
    </>
  );
}

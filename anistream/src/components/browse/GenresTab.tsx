import { AnimeCard } from "@/components/home/AnimeCard";
import { getSeriesList, getDiscoverSeries, consolidateFranchises } from "@/lib/series";
import type { SeriesListParams } from "@/lib/series";
import { topGenres } from "@/lib/genres";
import { FilterBar } from "@/components/browse/FilterBar";
import { getWatchlistIds } from "@/app/actions/watchlist";
import type { Series } from "@/types";
import styles from "@/app/browse/browse.module.css";

interface GenresTabProps {
  genre?: string;
  year?: string;
  season?: string;
}

export default async function GenresTab({ genre, year, season }: GenresTabProps) {
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

  const [watchlistIds] = await Promise.all([getWatchlistIds()]);
  const watchlistSet = new Set(watchlistIds);
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
              <AnimeCard series={s} isInWatchlist={watchlistSet.has(s.id)} />
            </div>
          ))}
        </div>
      )}
    </>
  );
}

export const dynamic = "force-dynamic";

import { HeroBanner } from "@/components/home/HeroBanner";
import { SeriesRow } from "@/components/home/SeriesRow";
import { ContinueWatchingRow } from "@/components/home/ContinueWatchingRow";
import { getSeriesList, getFeaturedSeries, consolidateFranchises } from "@/lib/series";
import { topGenres } from "@/lib/genres";
import { getWatchlistIds } from "@/app/actions/watchlist";
import { getContinueWatching } from "@/app/actions/watchProgress";
import { getRecommendations } from "@/app/actions/recommendations";
import type { Metadata } from "next";
import type { Genre } from "@/types";

export const metadata: Metadata = { title: "Home" };

export default async function HomePage() {
  const [allSeries, featured, watchlistIds, continueWatching, recs] = await Promise.all([
    getSeriesList(500),
    getFeaturedSeries(),
    getWatchlistIds(),
    getContinueWatching(),
    getRecommendations(),
  ]);

  const consolidated = consolidateFranchises(allSeries);

  const topPicks = consolidated.slice(0, 10);
  const simulcasts = consolidated.filter((s) => s.isSimulcast);
  const genres = topGenres(consolidated, 5);

  return (
    <>
      <HeroBanner featured={featured.length ? featured : allSeries.slice(0, 5)} watchlistIds={watchlistIds} />
      <div style={{ paddingTop: "var(--space-8)" }}>
        <ContinueWatchingRow episodes={continueWatching} />
        {recs.length > 0 && <SeriesRow title="Recommended for You" series={recs} />}
        <SeriesRow title="Top Picks for You" series={topPicks} />
        {simulcasts.length > 0 && (
          <SeriesRow title="Simulcasts" series={simulcasts} />
        )}
        <SeriesRow title="Popular" series={consolidated} />
        {genres.map((genre) => {
          const rows = consolidated
            .filter((s) => s.genres?.includes(genre as Genre))
            .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
            .slice(0, 10);
          return rows.length > 0 ? (
            <SeriesRow key={genre} title={`Top ${genre}`} series={rows} />
          ) : null;
        })}
      </div>
    </>
  );
}

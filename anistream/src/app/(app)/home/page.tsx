export const dynamic = "force-dynamic";

import { HeroBanner } from "@/components/home/HeroBanner";
import { SeriesRow } from "@/components/home/SeriesRow";
import { ContinueWatchingRow } from "@/components/home/ContinueWatchingRow";
import { getSeriesList, getFeaturedSeries, getSimulcastSeries } from "@/lib/series";
import { topGenres } from "@/lib/genres";
import { shuffle } from "@/lib/utils";
import { getWatchlistIds } from "@/app/actions/watchlist";
import { getContinueWatching } from "@/app/actions/watchProgress";
import { getRecommendations } from "@/app/actions/recommendations";
import type { Metadata } from "next";
import type { Genre } from "@/types";

export const metadata: Metadata = { title: "Home" };

export default async function HomePage() {
  const [series, featured, watchlistIds, continueWatching, recs, simulcasts] = await Promise.all([
    getSeriesList({ limit: 100, consolidated: true }),
    getFeaturedSeries(),
    getWatchlistIds(),
    getContinueWatching(),
    getRecommendations(),
    getSimulcastSeries(15),
  ]);

  const topPicks = shuffle(series).slice(0, 10);
  const genres = shuffle(topGenres(series, 10));
  const watchlistSet = new Set(watchlistIds);

  return (
    <>
      <HeroBanner featured={featured.length ? featured : series.slice(0, 5)} watchlistIds={watchlistIds} />
      <div className="home-content" style={{ paddingTop: "var(--space-8)" }}>
        <ContinueWatchingRow episodes={continueWatching} />
        {recs.length > 0 && <SeriesRow title="Recommended for You" series={recs} watchlistIds={watchlistSet} />}
        <SeriesRow title="Top Picks for You" series={topPicks} watchlistIds={watchlistSet} />
        {simulcasts.length > 0 && (
          <SeriesRow title="Simulcasts" series={shuffle(simulcasts)} watchlistIds={watchlistSet} />
        )}
        <SeriesRow title="Popular" series={series} limit={20} watchlistIds={watchlistSet} />
        {genres.map((genre) => {
          const rows = shuffle(series)
            .filter((s) => s.genres?.includes(genre as Genre))
            .slice(0, 10);
          return rows.length > 0 ? (
            <SeriesRow key={genre} title={`Top ${genre}`} series={rows} watchlistIds={watchlistSet} />
          ) : null;
        })}
      </div>
    </>
  );
}

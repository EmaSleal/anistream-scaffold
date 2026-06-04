export const dynamic = "force-dynamic";

import { HeroBanner } from "@/components/home/HeroBanner";
import { SeriesRow } from "@/components/home/SeriesRow";
import { ContinueWatchingRow } from "@/components/home/ContinueWatchingRow";
import { getSeriesList, getFeaturedSeries, consolidateFranchises } from "@/lib/series";
import { getWatchlistIds } from "@/app/actions/watchlist";
import { getContinueWatching } from "@/app/actions/watchProgress";
import { getRecommendations } from "@/app/actions/recommendations";
import type { Metadata } from "next";

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
  const isekai = consolidated.filter((s) => s.genres.includes("Isekai"));
  const action = consolidated.filter((s) => s.genres.includes("Action"));
  const simulcasts = consolidated.filter((s) => s.isSimulcast);

  return (
    <>
      <HeroBanner featured={featured.length ? featured : allSeries.slice(0, 5)} watchlistIds={watchlistIds} />
      <div style={{ paddingTop: "32px" }}>
        <ContinueWatchingRow episodes={continueWatching} />
        {recs.length > 0 && <SeriesRow title="Recommended for You" series={recs} />}
        <SeriesRow title="Top Picks for You" series={topPicks} />
        {simulcasts.length > 0 && (
          <SeriesRow title="Simulcasts" series={simulcasts} />
        )}
        {isekai.length > 0 && (
          <SeriesRow title="Isekai" series={isekai} />
        )}
        {action.length > 0 && (
          <SeriesRow title="Action" series={action} />
        )}
        <SeriesRow title="Popular" series={consolidated} />
      </div>
    </>
  );
}

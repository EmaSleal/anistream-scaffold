import { SeriesRow } from "@/components/home/SeriesRow";
import { getSimulcastSeries, consolidateFranchises } from "@/lib/series";
import { topGenres } from "@/lib/genres";
import type { Series } from "@/types";

export default async function SimulcastsTab() {
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

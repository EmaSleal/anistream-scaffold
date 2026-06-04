import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { auth } from "@/auth";
import { getSeriesById, getSeriesSeasons } from "@/lib/series";
import { isBroadcastDay, isCooldownElapsed } from "@/lib/simulcast";
import { SeriesBanner } from "@/components/series/SeriesBanner";
import { EpisodesSection } from "@/components/series/EpisodesSection";
import IngestTrigger from "./IngestTrigger";
import SimulcastRefreshTrigger from "./SimulcastRefreshTrigger";

interface SeriesPageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: SeriesPageProps): Promise<Metadata> {
  const { id } = await params;
  const series = await getSeriesById(id);
  return { title: series?.title ?? "Series" };
}

export default async function SeriesPage({ params }: SeriesPageProps) {
  const { id } = await params;
  const [series, session] = await Promise.all([getSeriesById(id), auth()]);
  const isAdmin = session?.user?.role === "ADMIN";

  if (!series) {
    if (isAdmin) redirect(`/admin?slug=${id}`);
    return (
      <div style={{ paddingTop: "120px", textAlign: "center", color: "rgba(255,255,255,0.5)" }}>
        Series not found.
      </div>
    );
  }

  const { seasons, initialSeasonIdx } = await getSeriesSeasons(id);
  const noEpisodes = seasons.length === 0;

  // Determine whether to fire a simulcast refresh trigger on the client.
  // All four conditions must hold; the check is non-blocking (page renders immediately).
  const shouldTriggerSimulcastRefresh =
    series.isSimulcast === true &&
    !!series.broadcastDay &&
    !!series.broadcastTime &&
    !!series.broadcastTimezone &&
    isBroadcastDay(series.broadcastDay, series.broadcastTime, series.broadcastTimezone) &&
    isCooldownElapsed(series.lastSimulcastCheck);

  return (
    <div>
      {shouldTriggerSimulcastRefresh && (
        <SimulcastRefreshTrigger seriesId={series.id} />
      )}
      <SeriesBanner series={series} />
      {!noEpisodes ? (
        <EpisodesSection seasons={seasons} initialSeasonIdx={initialSeasonIdx} />
      ) : isAdmin && series.malId ? (
        <IngestTrigger
          seriesId={series.id}
          malId={series.malId}
          animeflvSlug={series.animeflvSlug ?? null}
        />
      ) : (
        <p style={{ padding: "48px 24px", textAlign: "center", color: "rgba(255,255,255,0.4)", fontSize: "0.9rem" }}>
          No episodes available yet.
        </p>
      )}
    </div>
  );
}

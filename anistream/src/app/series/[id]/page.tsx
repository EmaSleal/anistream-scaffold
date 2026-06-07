import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { auth } from "@/auth";
import { getSeriesById, getSeriesSeasons, getSeriesByFranchiseId } from "@/lib/series";
import { isBroadcastDay, isCooldownElapsed } from "@/lib/simulcast";
import { SeriesBanner } from "@/components/series/SeriesBanner";
import { EpisodesSection } from "@/components/series/EpisodesSection";
import { FranchiseSection } from "@/components/series/FranchiseSection";
import { getEpisodeProgressMap, getLastWatchedInFranchise } from "@/lib/progress-server";
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

  const userId = session?.user?.id;

  const [{ seasons: rawSeasons, initialSeasonIdx }, franchiseMembers, progressMap] =
    await Promise.all([
      getSeriesSeasons(id),
      series.franchiseId ? getSeriesByFranchiseId(series.franchiseId) : Promise.resolve([]),
      userId
        ? getEpisodeProgressMap(series.id)
        : Promise.resolve(new Map<string, { progressSec: number; durationSec: number }>()),
    ]);

  const seasons = rawSeasons.map((s) => ({
    ...s,
    episodes: s.episodes.map((ep) => {
      const prog = progressMap.get(ep.id);
      if (!prog) return ep;
      const durationSec = prog.durationSec || ep.duration;
      const isSeen = durationSec > 0 && durationSec - prog.progressSec <= 120;
      return {
        ...ep,
        duration: durationSec,
        progressSeconds: prog.progressSec,
        isSeen,
      };
    }),
  }));

  const noEpisodes = seasons.length === 0;

  const showFranchise = franchiseMembers.length > 1;
  const lastWatchedInFranchise = showFranchise
    ? await getLastWatchedInFranchise(franchiseMembers.map((m) => m.id))
    : null;

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
      {showFranchise && (
        <FranchiseSection
          members={franchiseMembers}
          currentId={series.id}
          targetId={lastWatchedInFranchise}
        />
      )}
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

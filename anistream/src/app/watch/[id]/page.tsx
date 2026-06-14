import type { Metadata } from "next";
import type { Episode } from "@/types";
import { VideoPlayer } from "@/components/player/VideoPlayer";
import { getEpisodeProgress } from "@/app/actions/watchProgress";
import { getEpisodeByWatchId, getAdjacentEpisodes, getEpisodeStreamUrl } from "@/lib/episodes";
import { getEpisodeProgressMap } from "@/lib/progress-server";
import StreamFallbackModal from "@/components/player/StreamFallbackModal";

interface WatchPageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: WatchPageProps): Promise<Metadata> {
  const { id } = await params;
  const dbResult = await getEpisodeByWatchId(id);
  return {
    title: dbResult ? `${dbResult.episode.seriesTitle} – ${dbResult.episode.title}` : "Watch",
  };
}

export default async function WatchPage({ params }: WatchPageProps) {
  const { id } = await params;

  const dbResult = await getEpisodeByWatchId(id);
  if (!dbResult) {
    return (
      <div style={{ paddingTop: "calc(var(--nav-height) + 2rem)", textAlign: "center", color: "rgba(255,255,255,0.5)" }}>
        Episode not found.
      </div>
    );
  }

  const { episode } = dbResult;

  const [streamResult, initialProgress, adjacent, progressMap] = await Promise.all([
    getEpisodeStreamUrl(id),
    getEpisodeProgress(episode.id),
    getAdjacentEpisodes(episode.seriesId, episode.episode),
    getEpisodeProgressMap(episode.seriesId),
  ]);

  function enrichEpisode(ep: Episode | null): Episode | null {
    if (!ep) return null;
    const prog = progressMap.get(ep.id);
    if (!prog) return ep;
    return {
      ...ep,
      progressSeconds: prog.progressSec,
      isSeen: prog.durationSec > 0 && prog.durationSec - prog.progressSec <= 120,
    };
  }

  if (!streamResult) {
    return (
      <StreamFallbackModal
        seriesId={episode.seriesId}
        seriesTitle={episode.seriesTitle}
        episodeTitle={episode.title}
      />
    );
  }

  const streamType = streamResult.source === "animeav1" ? "hls" : "mp4";
  const streamUrl =
    streamResult.source === "animeflv"
      ? `/api/proxy/stream?url=${encodeURIComponent(streamResult.url)}`
      : streamResult.url;

  return (
    <VideoPlayer
      episode={episode}
      previousEpisode={enrichEpisode(adjacent.prev) ?? undefined}
      nextEpisode={enrichEpisode(adjacent.next) ?? undefined}
      initialProgress={initialProgress}
      streamUrl={streamUrl}
      streamType={streamType}
    />
  );
}

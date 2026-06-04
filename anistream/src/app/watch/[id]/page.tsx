import type { Metadata } from "next";
import { VideoPlayer } from "@/components/player/VideoPlayer";
import { getEpisodeProgress } from "@/app/actions/watchProgress";
import { getEpisodeByWatchId, getAdjacentEpisodes, getEpisodeStreamUrl } from "@/lib/episodes";
import StreamFallbackModal from "./StreamFallbackModal";

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
      <div style={{ paddingTop: "120px", textAlign: "center", color: "rgba(255,255,255,0.5)" }}>
        Episode not found.
      </div>
    );
  }

  const { episode } = dbResult;

  const [streamResult, initialProgress, adjacent] = await Promise.all([
    getEpisodeStreamUrl(id),
    getEpisodeProgress(episode.id),
    getAdjacentEpisodes(episode.seriesId, episode.episode),
  ]);

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

  return (
    <VideoPlayer
      episode={episode}
      previousEpisode={adjacent.prev ?? undefined}
      nextEpisode={adjacent.next ?? undefined}
      initialProgress={initialProgress}
      streamUrl={streamResult.url}
      streamType={streamType}
    />
  );
}

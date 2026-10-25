import type { Metadata } from "next";
import type { Episode } from "@/types";
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { auth } from "@/auth";
import { VideoPlayer } from "@/components/player/VideoPlayer";
import { getEpisodeProgress } from "@/app/actions/watchProgress";
import { getEpisodeByWatchId, getAdjacentEpisodes, getEpisodeStreamUrl } from "@/lib/episodes";
import { getEpisodeProgressMap } from "@/lib/progress-server";
import StreamFallbackModal from "@/components/player/StreamFallbackModal";
import { toDualAudioStream, toPlayableStream, type StreamSource, type StreamType } from "@/lib/stream-source";

function isSafari(userAgent: string): boolean {
  return /^((?!chrome|android).)*safari/i.test(userAgent);
}

interface WatchPageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: WatchPageProps): Promise<Metadata> {
  const { id } = await params;
  const dbResult = await getEpisodeByWatchId(id);
  return {
    title: dbResult ? `${dbResult.episode.seriesTitle} – ${dbResult.episode.title}` : "Watch",
    robots: { index: false, follow: false },
  };
}

export default async function WatchPage({ params }: WatchPageProps) {
  const session = await auth();
  if (!session) redirect("/");

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

  const headersList = await headers();
  const ua = headersList.get("user-agent") ?? "";
  const hint = isSafari(ua) ? "h264" : undefined;

  const [streamResult, initialProgress, adjacent, progressMap] = await Promise.all([
    getEpisodeStreamUrl(id, hint),
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

  // ---------------------------------------------------------------------------
  // Derive proxied URLs and stream type from the dual-audio or legacy result.
  // ---------------------------------------------------------------------------

  let streamUrl: string | undefined;
  let dubUrl: string | null = null;
  let audioFormats: ("sub" | "dub")[] = ["sub"];
  let streamType: StreamType;
  let streamSource: StreamSource;

  if ("subUrl" in streamResult) {
    // Dual-audio shape — DUB-capable AnimeAV1 series; SUB follows its own source.
    audioFormats = streamResult.audioFormats;
    ({ streamUrl, streamType, streamSource, dubUrl } = toDualAudioStream(streamResult));
  } else {
    // Legacy single-URL shape.
    streamSource = streamResult.source;
    ({ url: streamUrl, type: streamType } = toPlayableStream(streamResult.source, streamResult.url));
  }

  return (
    <VideoPlayer
      episode={episode}
      previousEpisode={enrichEpisode(adjacent.prev) ?? undefined}
      nextEpisode={enrichEpisode(adjacent.next) ?? undefined}
      initialProgress={initialProgress}
      streamUrl={streamUrl}
      dubUrl={dubUrl}
      audioFormats={audioFormats}
      streamType={streamType}
      streamSource={streamSource}
    />
  );
}

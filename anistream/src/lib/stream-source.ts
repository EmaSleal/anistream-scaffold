// ---------------------------------------------------------------------------
// Per-source mapping from a Flask stream URL to what the player can load.
// Shared by the legacy single-URL and the dual-audio branches of the watch page.
// ---------------------------------------------------------------------------

export type StreamSource = "animeflv" | "jkanime" | "animeav1" | "nas";
export type StreamType = "hls" | "mp4";

export interface PlayableStream {
  url: string;
  type: StreamType;
}

export function toPlayableStream(source: StreamSource, rawUrl: string): PlayableStream {
  const encoded = encodeURIComponent(rawUrl);
  switch (source) {
    case "jkanime":
      return { url: rawUrl, type: "hls" };
    case "animeav1":
      // Zilla CDN requires Referer: https://animeav1.com/ — proxy through Next.js.
      return { url: `/api/stream/animeav1-proxy?path=${encoded}`, type: "hls" };
    case "nas":
      // NAS download requires X-API-Key — proxy through Next.js.
      return { url: `/api/proxy/nas-file?url=${encoded}`, type: "mp4" };
    case "animeflv":
      // Streamtape — proxy through Next.js to fix iOS Referer restriction.
      return { url: `/api/proxy/stream?url=${encoded}`, type: "mp4" };
  }
}

export interface DualAudioInput {
  subUrl: string | null;
  subSource: StreamSource | null;
  dubUrl: string | null;
}

export interface DualAudioStream {
  streamUrl: string | undefined;
  streamType: StreamType;
  streamSource: StreamSource;
  dubUrl: string | null;
}

/**
 * Derive player inputs from the dual-audio response. SUB follows its own source;
 * DUB comes only from AnimeAV1, so it is always proxied as AnimeAV1 HLS. When SUB
 * is unavailable, the player starts on DUB, so source and type are AnimeAV1's.
 */
export function toDualAudioStream({ subUrl, subSource, dubUrl }: DualAudioInput): DualAudioStream {
  const dub = dubUrl ? toPlayableStream("animeav1", dubUrl).url : null;

  if (subUrl && subSource) {
    const sub = toPlayableStream(subSource, subUrl);
    return { streamUrl: sub.url, streamType: sub.type, streamSource: subSource, dubUrl: dub };
  }

  return { streamUrl: undefined, streamType: "hls", streamSource: "animeav1", dubUrl: dub };
}

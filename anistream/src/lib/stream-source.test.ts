import { describe, it, expect } from "vitest";
import { toPlayableStream, toDualAudioStream } from "./stream-source";

const RAW = "https://cdn.example.com/video.m3u8";
const ENC = encodeURIComponent(RAW);

// ---------------------------------------------------------------------------
// toPlayableStream — per-source URL and stream type (legacy mapping)
// ---------------------------------------------------------------------------

describe("toPlayableStream", () => {
  it("jkanime: raw URL, hls", () => {
    expect(toPlayableStream("jkanime", RAW)).toEqual({ url: RAW, type: "hls" });
  });

  it("animeav1: animeav1-proxy, hls", () => {
    expect(toPlayableStream("animeav1", RAW)).toEqual({
      url: `/api/stream/animeav1-proxy?path=${ENC}`,
      type: "hls",
    });
  });

  it("nas: nas-file proxy, mp4", () => {
    expect(toPlayableStream("nas", RAW)).toEqual({
      url: `/api/proxy/nas-file?url=${ENC}`,
      type: "mp4",
    });
  });

  it("animeflv: stream proxy, mp4", () => {
    expect(toPlayableStream("animeflv", RAW)).toEqual({
      url: `/api/proxy/stream?url=${ENC}`,
      type: "mp4",
    });
  });

  it("encodes ?, & and spaces in proxied URLs", () => {
    const raw = "https://nas.example.com/files/my file.mp4?id=1&key=a b";
    const { url } = toPlayableStream("nas", raw);
    expect(url).toBe(
      "/api/proxy/nas-file?url=https%3A%2F%2Fnas.example.com%2Ffiles%2Fmy%20file.mp4%3Fid%3D1%26key%3Da%20b",
    );
    expect(decodeURIComponent(url.split("?url=")[1])).toBe(raw);
  });
});

// ---------------------------------------------------------------------------
// toDualAudioStream — dual-audio response shape
// ---------------------------------------------------------------------------

const DUB_RAW = "https://player.zilla-networks.com/m3u8/dub";
const DUB_PROXIED = `/api/stream/animeav1-proxy?path=${encodeURIComponent(DUB_RAW)}`;

describe("toDualAudioStream", () => {
  it("jkanime subSource is not routed through animeav1-proxy", () => {
    expect(
      toDualAudioStream({ subUrl: RAW, subSource: "jkanime", dubUrl: DUB_RAW }),
    ).toEqual({ streamUrl: RAW, streamType: "hls", streamSource: "jkanime", dubUrl: DUB_PROXIED });
  });

  it("nas subSource goes through nas-file as mp4", () => {
    expect(
      toDualAudioStream({ subUrl: RAW, subSource: "nas", dubUrl: DUB_RAW }),
    ).toEqual({
      streamUrl: `/api/proxy/nas-file?url=${ENC}`,
      streamType: "mp4",
      streamSource: "nas",
      dubUrl: DUB_PROXIED,
    });
  });

  it("animeav1 subSource goes through animeav1-proxy as hls", () => {
    expect(
      toDualAudioStream({ subUrl: RAW, subSource: "animeav1", dubUrl: null }),
    ).toEqual({
      streamUrl: `/api/stream/animeav1-proxy?path=${ENC}`,
      streamType: "hls",
      streamSource: "animeav1",
      dubUrl: null,
    });
  });

  it("subUrl null with DUB present: no stream URL, hls, source animeav1", () => {
    expect(
      toDualAudioStream({ subUrl: null, subSource: null, dubUrl: DUB_RAW }),
    ).toEqual({ streamUrl: undefined, streamType: "hls", streamSource: "animeav1", dubUrl: DUB_PROXIED });
  });
});

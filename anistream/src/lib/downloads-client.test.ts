import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchDownloadedEpisodes } from "./downloads-client";

afterEach(() => vi.unstubAllGlobals());

describe("fetchDownloadedEpisodes", () => {
  it("returns the episode numbers on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ episodeNumbers: [1, 2, 5] }),
    });
    vi.stubGlobal("fetch", fetchMock);
    expect(await fetchDownloadedEpisodes("s1")).toEqual([1, 2, 5]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/series/s1/downloaded-episodes");
  });

  it("returns [] on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }));
    expect(await fetchDownloadedEpisodes("s1")).toEqual([]);
  });

  it("returns [] on network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    expect(await fetchDownloadedEpisodes("s1")).toEqual([]);
  });

  it("returns [] on a malformed body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
    expect(await fetchDownloadedEpisodes("s1")).toEqual([]);
  });
});

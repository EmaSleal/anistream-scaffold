import { afterEach, describe, expect, it, vi } from "vitest";
import {
  enqueueErrorMessage,
  enqueueSeries,
  fetchDownloadedEpisodes,
  fetchSeriesQueue,
  summarizeQueue,
  type QueueItem,
} from "./downloads-client";

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

describe("enqueueSeries", () => {
  it("POSTs and returns the counts", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ queued: 3, alreadyQueued: 1 }),
    });
    vi.stubGlobal("fetch", fetchMock);
    expect(await enqueueSeries("s1")).toEqual({ queued: 3, alreadyQueued: 1 });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/downloads/series/s1/enqueue");
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
  });

  it("throws the server error on a non-OK response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ error: "Forbidden" }) })
    );
    await expect(enqueueSeries("s1")).rejects.toThrow("Forbidden");
  });
});

describe("enqueueErrorMessage", () => {
  it("explains a missing jkanime slug", () => {
    expect(enqueueErrorMessage(new Error("no_jkanime_slug"))).toMatch(/slug de jkanime/);
  });

  it("falls back to a generic message", () => {
    expect(enqueueErrorMessage(new Error("HTTP 500"))).toBe("No se pudo encolar la serie. Intentá de nuevo.");
    expect(enqueueErrorMessage("boom")).toBe("No se pudo encolar la serie. Intentá de nuevo.");
  });
});

describe("fetchSeriesQueue", () => {
  it("returns the items and omits downloadedEpisodes when absent", async () => {
    const items = [{ episodeNumber: 1, status: "queued", error: null }];
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items }) });
    vi.stubGlobal("fetch", fetchMock);
    expect(await fetchSeriesQueue("s1")).toEqual({ items });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/downloads/series/s1/queue");
  });

  it("includes downloadedEpisodes when the server sends it", async () => {
    const items = [{ episodeNumber: 1, status: "done", error: null }];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items, downloadedEpisodes: [1, 2] }) })
    );
    expect(await fetchSeriesQueue("s1")).toEqual({ items, downloadedEpisodes: [1, 2] });
  });

  it("returns empty items on non-OK, network error or malformed body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }));
    expect(await fetchSeriesQueue("s1")).toEqual({ items: [] });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    expect(await fetchSeriesQueue("s1")).toEqual({ items: [] });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
    expect(await fetchSeriesQueue("s1")).toEqual({ items: [] });
  });
});

describe("summarizeQueue", () => {
  const item = (n: number, status: QueueItem["status"]): QueueItem => ({
    episodeNumber: n,
    status,
    error: null,
  });

  it("counts queued, finds the downloading episode and flags active", () => {
    const s = summarizeQueue([item(1, "done"), item(2, "downloading"), item(3, "queued"), item(4, "queued")]);
    expect(s).toEqual({ queued: 2, downloadingEpisodes: [2], failed: 0, active: true });
  });

  it("lists every downloading episode in ascending order", () => {
    const s = summarizeQueue([item(4, "downloading"), item(3, "downloading"), item(5, "queued")]);
    expect(s).toEqual({ queued: 1, downloadingEpisodes: [3, 4], failed: 0, active: true });
  });

  it("is inactive when nothing is queued or downloading", () => {
    const s = summarizeQueue([item(1, "done"), item(2, "failed")]);
    expect(s).toMatchObject({ active: false, failed: 1, downloadingEpisodes: [] });
  });

  it("ignores a failed row superseded by a later retry", () => {
    const s = summarizeQueue([item(1, "failed"), item(1, "done")]);
    expect(s.failed).toBe(0);
  });
});

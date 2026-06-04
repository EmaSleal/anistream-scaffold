/**
 * Vitest unit tests for src/app/actions/recommendations.ts
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// ---------------------------------------------------------------------------
// Mock next/headers before importing the module under test
// ---------------------------------------------------------------------------
vi.mock("next/headers", () => ({
  cookies: vi.fn().mockResolvedValue({
    getAll: () => [{ name: "session", value: "abc123" }],
  }),
}));

// ---------------------------------------------------------------------------
// Import after mocks are set up
// ---------------------------------------------------------------------------
import { getRecommendations } from "./recommendations";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSeries(partial: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    id: "s1",
    title: "Test Anime",
    slug: "test-anime",
    description: "A test series.",
    thumbnailUrl: "http://img/s1.jpg",
    bannerUrl: "",
    rating: "14+",
    genres: ["Action"],
    audioFormats: ["sub"],
    seasonCount: 1,
    episodeCount: 12,
    year: 2024,
    isSimulcast: false,
    isFeatured: false,
    ...partial,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("getRecommendations", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns empty array when response is 401", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ error: "Unauthorized" }),
      })
    );

    const result = await getRecommendations();
    expect(result).toEqual([]);
  });

  it("returns empty array when response is 500", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ error: "Internal Server Error" }),
      })
    );

    const result = await getRecommendations();
    expect(result).toEqual([]);
  });

  it("returns mapped Series[] on 200", async () => {
    const series = [makeSeries({ id: "s1" }), makeSeries({ id: "s2" })];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => series,
      })
    );

    const result = await getRecommendations();
    expect(result).toHaveLength(2);
    expect(result[0]).toMatchObject({ id: "s1", title: "Test Anime" });
    expect(result[1]).toMatchObject({ id: "s2" });
  });

  it("returns empty array when fetch throws", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network failure")));

    const result = await getRecommendations();
    expect(result).toEqual([]);
  });

  it("calls the correct endpoint URL", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    });
    vi.stubGlobal("fetch", mockFetch);

    await getRecommendations();

    expect(mockFetch).toHaveBeenCalledOnce();
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/api/recommendations");
  });
});

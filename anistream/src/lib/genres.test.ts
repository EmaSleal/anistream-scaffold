import { describe, it, expect } from "vitest";
import { topGenres } from "./genres";
import type { Series } from "@/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSeries(id: string, genres: string[]): Series {
  return {
    id,
    title: `Series ${id}`,
    slug: id,
    description: "",
    thumbnailUrl: "",
    bannerUrl: "",
    rating: "14+",
    genres: genres as Series["genres"],
    audioFormats: ["sub"],
    seasonCount: 1,
    episodeCount: 12,
    year: 2024,
    isSimulcast: false,
    isFeatured: false,
    score: undefined,
    malId: undefined,
    animeflvSlug: undefined,
    franchiseId: undefined,
    seasonOrder: undefined,
    franchiseRelation: undefined,
    mediaType: "tv",
    animeflvDisabled: false,
    broadcastDay: undefined,
    broadcastTime: undefined,
    broadcastTimezone: undefined,
    airedFrom: undefined,
    kitsuStatus: undefined,
    lastSimulcastCheck: undefined,
  };
}

// ---------------------------------------------------------------------------
// topGenres
// ---------------------------------------------------------------------------

describe("topGenres", () => {
  it("returns genres sorted by frequency descending", () => {
    const series = [
      makeSeries("s1", ["Action", "Adventure"]),
      makeSeries("s2", ["Action", "Comedy"]),
      makeSeries("s3", ["Action", "Romance"]),
      makeSeries("s4", ["Comedy", "Romance"]),
      makeSeries("s5", ["Comedy"]),
    ];
    // Action=3, Comedy=3 (tie, insertion order), Romance=2, Adventure=1
    const result = topGenres(series, 4);
    expect(result[0]).toBe("Action");
    expect(result[1]).toBe("Comedy");
    expect(result).toContain("Romance");
    expect(result).toContain("Adventure");
    expect(result).toHaveLength(4);
  });

  it("returns only available genres when catalog has fewer than n", () => {
    const series = [
      makeSeries("s1", ["Isekai"]),
      makeSeries("s2", ["Isekai"]),
      makeSeries("s3", ["Fantasy"]),
    ];
    const result = topGenres(series, 5);
    expect(result).toHaveLength(2);
    expect(result).toContain("Isekai");
    expect(result).toContain("Fantasy");
  });

  it("returns empty array for empty series input", () => {
    expect(topGenres([], 5)).toEqual([]);
  });

  it("returns at most n genres when n < total distinct genres", () => {
    const series = [
      makeSeries("s1", ["A", "B", "C", "D", "E", "F"]),
    ];
    const result = topGenres(series, 3);
    expect(result).toHaveLength(3);
  });

  it("handles series with no genres gracefully", () => {
    const series = [
      makeSeries("s1", []),
      makeSeries("s2", ["Action"]),
    ];
    const result = topGenres(series, 5);
    expect(result).toEqual(["Action"]);
  });
});

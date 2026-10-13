/**
 * Vitest unit tests for src/app/actions/simulcast-admin.ts — getUnresolvedGaps()
 * (simulcast-gap-recovery Phase 4, admin visibility).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// ---------------------------------------------------------------------------
// Mock next/headers before importing the module under test
// ---------------------------------------------------------------------------
vi.mock("next/headers", () => ({
  cookies: vi.fn().mockResolvedValue({
    toString: () => "session=abc123",
  }),
}));

// ---------------------------------------------------------------------------
// Import after mocks are set up
// ---------------------------------------------------------------------------
import { getUnresolvedGaps } from "./simulcast-admin";

describe("getUnresolvedGaps", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns mapped UnresolvedGap[] on 200", async () => {
    const gaps = [
      {
        id: "daemons",
        title: "Daemons of the Shadow Realm",
        gapUnresolvedAt: "2026-10-01T00:00:00+00:00",
        gapMissingEpisodes: [1, 2],
        episodeCount: 12,
        principalSlug: "daemons",
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => gaps,
      }),
    );

    const result = await getUnresolvedGaps();
    expect(result).toEqual(gaps);
  });

  it("returns empty array on 200 with empty body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => [],
      }),
    );

    const result = await getUnresolvedGaps();
    expect(result).toEqual([]);
  });

  it("throws when the response is not ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        json: async () => ({ error: "Forbidden: admin role required" }),
      }),
    );

    await expect(getUnresolvedGaps()).rejects.toThrow(
      "Forbidden: admin role required",
    );
  });

  it("calls the correct endpoint URL", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    });
    vi.stubGlobal("fetch", mockFetch);

    await getUnresolvedGaps();

    expect(mockFetch).toHaveBeenCalledOnce();
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/api/admin/simulcast/gaps");
  });
});

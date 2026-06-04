/**
 * Vitest unit tests for src/lib/simulcast.ts
 *
 * Run with: pnpm vitest (requires vitest to be installed as devDependency)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { isBroadcastDay, isCooldownElapsed } from "./simulcast";

// ---------------------------------------------------------------------------
// isBroadcastDay
// ---------------------------------------------------------------------------

describe("isBroadcastDay", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns true when now is within +4h of broadcast UTC (in-window)", () => {
    // Spec anchor: "Wednesdays 00:00 JST" = Tuesday 15:00 UTC.
    // ±12h window: Mon 03:00 UTC to Wed 03:00 UTC.
    // We test: Tuesday 19:00 UTC — within window.

    // Find the most recent Tuesday at 19:00 UTC relative to a known reference.
    // Use a fixed known Tuesday: 2024-01-02 (a Tuesday).
    const fixedNow = new Date("2024-01-02T19:00:00Z"); // Tuesday 19:00 UTC
    vi.useFakeTimers();
    vi.setSystemTime(fixedNow);

    const result = isBroadcastDay("Wednesdays", "00:00", "Asia/Tokyo");
    // Tuesday 19:00 UTC is 4h after Tuesday 15:00 UTC → within ±12h
    expect(result).toBe(true);
  });

  it("returns false when now is outside the broadcast window (out-of-window)", () => {
    // Thursday 10:00 UTC: 19 hours after Tuesday 15:00 UTC — outside the ±12h window.
    const fixedNow = new Date("2024-01-04T10:00:00Z"); // Thursday 10:00 UTC
    vi.useFakeTimers();
    vi.setSystemTime(fixedNow);

    const result = isBroadcastDay("Wednesdays", "00:00", "Asia/Tokyo");
    expect(result).toBe(false);
  });

  it("returns false for an unknown day string", () => {
    const fixedNow = new Date("2024-01-02T19:00:00Z");
    vi.useFakeTimers();
    vi.setSystemTime(fixedNow);

    expect(isBroadcastDay("Whenever", "00:00", "Asia/Tokyo")).toBe(false);
  });

  it("returns false for an invalid time string", () => {
    const fixedNow = new Date("2024-01-02T19:00:00Z");
    vi.useFakeTimers();
    vi.setSystemTime(fixedNow);

    expect(isBroadcastDay("Wednesdays", "invalid", "Asia/Tokyo")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// isCooldownElapsed
// ---------------------------------------------------------------------------

describe("isCooldownElapsed", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns true when lastSimulcastCheck is undefined", () => {
    expect(isCooldownElapsed(undefined)).toBe(true);
  });

  it("returns true when lastSimulcastCheck is an empty string", () => {
    expect(isCooldownElapsed("")).toBe(true);
  });

  it("returns false when last check was 30 minutes ago (still in cooldown)", () => {
    const thirtyMinutesAgo = new Date(Date.now() - 30 * 60 * 1000).toISOString();
    expect(isCooldownElapsed(thirtyMinutesAgo)).toBe(false);
  });

  it("returns true when last check was 61 minutes ago (cooldown elapsed)", () => {
    const sixtyOneMinutesAgo = new Date(Date.now() - 61 * 60 * 1000).toISOString();
    expect(isCooldownElapsed(sixtyOneMinutesAgo)).toBe(true);
  });

  it("returns true when last check was exactly 3600s + 1ms ago", () => {
    const justPast = new Date(Date.now() - (3600 * 1000 + 1)).toISOString();
    expect(isCooldownElapsed(justPast)).toBe(true);
  });

  it("returns false when last check was exactly 3599s ago (still in cooldown)", () => {
    const justUnder = new Date(Date.now() - 3599 * 1000).toISOString();
    expect(isCooldownElapsed(justUnder)).toBe(false);
  });

  it("returns true for an invalid date string", () => {
    expect(isCooldownElapsed("not-a-date")).toBe(true);
  });
});

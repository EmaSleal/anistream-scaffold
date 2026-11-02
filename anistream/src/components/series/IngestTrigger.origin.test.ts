/**
 * ADR-016: IngestTrigger must keep using the non-admin ingestSeries action,
 * whose slug is only a guess and carries no admin-origin marker.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it, expect } from "vitest";

describe("IngestTrigger slug origin", () => {
  const src = readFileSync(join(__dirname, "IngestTrigger.tsx"), "utf8");

  it("calls ingestSeries and never the admin variant", () => {
    expect(src).toMatch(/ingestSeries\(/);
    expect(src).not.toMatch(/ingestSeriesAsAdmin/);
  });
});

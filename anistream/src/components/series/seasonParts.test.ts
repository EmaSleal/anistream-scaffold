import { describe, expect, it } from "vitest";
import { partsOf, selectPart, showPartTabs, type PartedSeason } from "./seasonParts";

const ep = (id: string, seriesId: string) => ({ id, seriesId });

const single: PartedSeason<{ id: string; seriesId: string }> = {
  label: "Temporada 1",
  seriesId: "a",
  episodes: [ep("e1", "a")],
  parts: [{ seriesId: "a", label: "Parte 1", episodes: [ep("e1", "a")] }],
};

const multi: PartedSeason<{ id: string; seriesId: string }> = {
  label: "Temporada 2",
  seriesId: "p1",
  episodes: [ep("a1", "p1")],
  parts: [
    { seriesId: "p1", label: "Parte 1", episodes: [ep("a1", "p1")] },
    { seriesId: "p2", label: "Parte 2", episodes: [ep("b1", "p2"), ep("b2", "p2")] },
  ],
};

describe("seasonParts", () => {
  it("single-part season shows no tabs and keeps its episodes and seriesId", () => {
    expect(showPartTabs(single)).toBe(false);
    const sel = selectPart(single, 0);
    expect(sel.seriesId).toBe("a");
    expect(sel.part.episodes).toEqual(single.episodes);
  });

  it("multi-part season shows tabs and switching part changes episodes and seriesId", () => {
    expect(showPartTabs(multi)).toBe(true);
    expect(selectPart(multi, 0).seriesId).toBe("p1");
    const second = selectPart(multi, 1);
    expect(second.seriesId).toBe("p2");
    expect(second.part.episodes.map((e) => e.id)).toEqual(["b1", "b2"]);
  });

  it("clamps an out-of-range part index", () => {
    expect(selectPart(multi, 5).partIdx).toBe(1);
    expect(selectPart(multi, -1).partIdx).toBe(0);
  });

  it("falls back to a single part when `parts` is missing", () => {
    const legacy: PartedSeason<{ id: string; seriesId: string }> = {
      label: "Temporada 1",
      episodes: [ep("e1", "z")],
    };
    expect(partsOf(legacy)).toHaveLength(1);
    expect(showPartTabs(legacy)).toBe(false);
    // seriesId falls back to the first episode's, as before
    expect(selectPart(legacy, 0).seriesId).toBe("z");
  });
});

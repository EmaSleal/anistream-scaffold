// Part selection for a season (ADR-023): a season with more than one cour part
// shows tabs; each part carries its own episodes and seriesId (the id used for
// the admin download/queue actions).

export interface SeasonPart<E extends { seriesId?: string } = { seriesId?: string }> {
  seriesId?: string;
  label: string;
  episodes: E[];
}

export interface PartedSeason<E extends { seriesId?: string } = { seriesId?: string }> {
  label: string;
  seriesId?: string;
  episodes: E[];
  parts?: SeasonPart<E>[];
}

/** The season's parts; a season without `parts` is treated as a single part. */
export function partsOf<E extends { seriesId?: string }>(season: PartedSeason<E>): SeasonPart<E>[] {
  if (season.parts && season.parts.length > 0) return season.parts;
  return [{ seriesId: season.seriesId, label: season.label, episodes: season.episodes }];
}

/** Tabs are shown only when the season has more than one part. */
export function showPartTabs<E extends { seriesId?: string }>(season: PartedSeason<E>): boolean {
  return partsOf(season).length > 1;
}

/** The selected part (index clamped to range) and the seriesId actions should target. */
export function selectPart<E extends { seriesId?: string }>(
  season: PartedSeason<E>,
  partIdx: number,
): { part: SeasonPart<E>; partIdx: number; seriesId: string | undefined } {
  const parts = partsOf(season);
  const idx = Math.min(Math.max(partIdx, 0), parts.length - 1);
  const part = parts[idx];
  return { part, partIdx: idx, seriesId: part.seriesId ?? part.episodes[0]?.seriesId };
}

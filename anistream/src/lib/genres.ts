import type { Series } from "@/types";

/**
 * Returns the top `n` genre names from the given series array,
 * sorted by frequency (most common first).
 *
 * Pure function — no network calls, no side effects.
 */
export function topGenres(series: Series[], n: number): string[] {
  const counts = new Map<string, number>();
  for (const s of series) {
    for (const g of s.genres) {
      counts.set(g, (counts.get(g) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([genre]) => genre);
}

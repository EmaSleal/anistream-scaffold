/**
 * Pure iOS detection utility. Safe to import server-side — no `window` access at module level.
 *
 * Heuristic:
 *   - UA contains iPhone / iPad / iPod, OR
 *   - UA does NOT contain Windows / Linux / CrOS / Android AND maxTouchPoints > 1
 *   (covers iPadOS ≥ 13 "desktop" mode which reports a Mac UA)
 */
export function isIosClient(ua: string, maxTouchPoints: number): boolean {
  if (/iPhone|iPad|iPod/.test(ua)) return true;
  if (!/Windows|Linux|CrOS|Android/.test(ua) && maxTouchPoints > 1) return true;
  return false;
}

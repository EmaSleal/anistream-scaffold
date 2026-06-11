/**
 * Format seconds into MM:SS or HH:MM:SS
 */
export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);

  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");

  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/**
 * Clamp a number between min and max
 */
export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

/**
 * Calculate progress percentage 0–100
 */
export function calcProgress(current: number, total: number): number {
  if (total === 0) return 0;
  return clamp((current / total) * 100, 0, 100);
}

/**
 * Throttle a function
 */
export function throttle<T extends (...args: unknown[]) => void>(
  fn: T,
  delay: number
): T {
  let lastCall = 0;
  return ((...args: unknown[]) => {
    const now = Date.now();
    if (now - lastCall >= delay) {
      lastCall = now;
      fn(...args);
    }
  }) as T;
}

/**
 * Debounce a function
 */
export function debounce<T extends (...args: unknown[]) => void>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout>;
  return (...args: Parameters<T>) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

/**
 * Format episode label e.g. "E5" or "S2 E3"
 */
export function formatEpisodeLabel(
  episode: number,
  season?: number
): string {
  return season && season > 1 ? `S${season} E${episode}` : `E${episode}`;
}

/**
 * Safe classnames join (no external dep needed)
 */
export function cn(...classes: (string | undefined | false | null)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function shuffle<T>(arr: T[]): T[] {
  const out = [...arr];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

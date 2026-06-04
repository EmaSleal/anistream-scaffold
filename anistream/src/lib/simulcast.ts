/**
 * Client-side simulcast helper utilities.
 *
 * These run in a browser/Node.js context using the Web Platform APIs
 * (Intl.DateTimeFormat) — no server-only imports.
 */

const BROADCAST_WINDOW_HOURS = 12;

// Maps the Jikan day string (lowercase) to a JS getUTCDay() value.
// JS: 0 = Sunday, 1 = Monday, …, 6 = Saturday
// Jikan: "Mondays" = Monday, etc.
const DAY_NAME_TO_JS_DAY: Record<string, number> = {
  sundays: 0,
  mondays: 1,
  tuesdays: 2,
  wednesdays: 3,
  thursdays: 4,
  fridays: 5,
  saturdays: 6,
};

/**
 * Convert a Jikan-style broadcast day + local time to a UTC timestamp (ms).
 *
 * Strategy:
 * 1. Take the current UTC date and find the most recent occurrence of `dayName`
 *    (same week or today).
 * 2. Combine with the local time string using `Intl.DateTimeFormat` to resolve
 *    the UTC offset for `timezone` on that date.
 * 3. Return the resulting UTC timestamp.
 *
 * @param broadcastDay  Jikan day string, e.g. "Wednesdays".
 * @param broadcastTime HH:MM string in the broadcast timezone.
 * @param timezone      IANA timezone, e.g. "Asia/Tokyo".
 * @returns UTC timestamp in milliseconds, or null if inputs are invalid.
 */
function getBroadcastUtcMs(
  broadcastDay: string,
  broadcastTime: string,
  timezone: string,
): number | null {
  const jsDayTarget = DAY_NAME_TO_JS_DAY[broadcastDay.toLowerCase().trim()];
  if (jsDayTarget === undefined) return null;

  const timeParts = broadcastTime.split(":");
  if (timeParts.length < 2) return null;
  const hour = parseInt(timeParts[0], 10);
  const minute = parseInt(timeParts[1], 10);
  if (isNaN(hour) || isNaN(minute)) return null;

  try {
    const now = new Date();

    // Get current date parts and weekday IN the broadcast timezone, not UTC.
    // This is critical: "Wednesdays 00:00 JST" is already Wednesday in JST even
    // though it falls on a Tuesday in UTC — using UTC weekday would walk back
    // to the wrong week.
    const formatter = new Intl.DateTimeFormat("en-US", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      weekday: "short",
      hour12: false,
    });

    const parts = formatter.formatToParts(now);
    const weekdayStr = parts.find((p) => p.type === "weekday")?.value ?? "";

    const SHORT_WEEKDAY_TO_JS: Record<string, number> = {
      Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6,
    };
    const currentTzDay = SHORT_WEEKDAY_TO_JS[weekdayStr];
    if (currentTzDay === undefined) return null;

    // Walk back to the most recent occurrence of the target weekday in the local tz.
    const daysBack = (currentTzDay - jsDayTarget + 7) % 7;

    const localYear = parseInt(parts.find((p) => p.type === "year")?.value ?? "0", 10);
    const localMonth = parseInt(parts.find((p) => p.type === "month")?.value ?? "1", 10) - 1;
    const localDay = parseInt(parts.find((p) => p.type === "day")?.value ?? "1", 10);

    // Build the target local date (JS handles day-of-month overflow/underflow).
    const targetDate = new Date(Date.UTC(localYear, localMonth, localDay - daysBack));
    const tYear = targetDate.getUTCFullYear();
    const tMonth = targetDate.getUTCMonth() + 1;
    const tDay = targetDate.getUTCDate();

    // Construct ISO string for the broadcast moment and correct for the timezone offset.
    const isoLocal = `${tYear}-${String(tMonth).padStart(2, "0")}-${String(tDay).padStart(2, "0")}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00`;
    const utcGuess = new Date(isoLocal + "Z").getTime();
    const offsetMs = getTimezoneOffsetMs(timezone, new Date(utcGuess));
    return utcGuess - offsetMs;
  } catch {
    return null;
  }
}

/**
 * Return the UTC offset in milliseconds for `timezone` at `date`.
 * Positive value means the timezone is AHEAD of UTC (e.g. JST = +9h = +32400000 ms).
 */
function getTimezoneOffsetMs(timezone: string, date: Date): number {
  // Trick: format the date in UTC and in the target timezone, then compare.
  const utcStr = date.toLocaleString("en-US", { timeZone: "UTC" });
  const tzStr = date.toLocaleString("en-US", { timeZone: timezone });
  const utcDate = new Date(utcStr);
  const tzDate = new Date(tzStr);
  return tzDate.getTime() - utcDate.getTime();
}

/**
 * Determine whether `now` falls within the ±12-hour broadcast window.
 *
 * Spec: "Wednesdays 00:00 JST" = Tuesday 15:00 UTC; ±12h → Mon 03:00 UTC to
 * Wed 03:00 UTC.
 *
 * @param broadcastDay       Jikan day string, e.g. "Wednesdays".
 * @param broadcastTime      HH:MM in the broadcast timezone.
 * @param broadcastTimezone  IANA timezone, e.g. "Asia/Tokyo".
 * @returns true if the current UTC time is within ±12h of the broadcast UTC time.
 */
export function isBroadcastDay(
  broadcastDay: string,
  broadcastTime: string,
  broadcastTimezone: string,
): boolean {
  const broadcastUtcMs = getBroadcastUtcMs(broadcastDay, broadcastTime, broadcastTimezone);
  if (broadcastUtcMs === null) return false;

  const nowMs = Date.now();
  const windowMs = BROADCAST_WINDOW_HOURS * 60 * 60 * 1000;
  return Math.abs(nowMs - broadcastUtcMs) <= windowMs;
}

/**
 * Return true when the simulcast cooldown has elapsed (or was never set).
 *
 * The cooldown is 3600 seconds (1 hour). A missing/undefined value means the
 * check has never run, so refresh is always allowed.
 *
 * @param lastSimulcastCheck ISO 8601 string from the series row, or undefined.
 * @returns true if a refresh is permitted, false if still in cooldown.
 */
export function isCooldownElapsed(lastSimulcastCheck: string | undefined): boolean {
  if (!lastSimulcastCheck) return true;
  const lastCheck = new Date(lastSimulcastCheck).getTime();
  if (isNaN(lastCheck)) return true;
  const ageSeconds = (Date.now() - lastCheck) / 1000;
  return ageSeconds > 3600;
}

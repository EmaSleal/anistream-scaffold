"use server";

/**
 * Server Action: fire-and-forget simulcast refresh.
 *
 * Calls the Flask simulcast refresh endpoint without blocking the caller.
 * All errors are swallowed — this is intentionally fire-and-forget.
 */
export async function refreshSimulcastAction(seriesId: string): Promise<void> {
  const flaskUrl = process.env.FLASK_URL ?? "http://localhost:5000";
  const serviceKey = process.env.SERVICE_SECRET ?? "";

  try {
    await fetch(`${flaskUrl}/api/simulcast/refresh/${seriesId}`, {
      method: "POST",
      headers: {
        "X-Service-Key": serviceKey,
      },
      cache: "no-store",
    });
  } catch {
    // Swallow all errors — fire-and-forget contract.
  }
}

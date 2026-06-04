/**
 * Shared server-only utility for proxying requests to the Flask backend.
 *
 * IMPORTANT: FLASK_URL is a server-only env var (no NEXT_PUBLIC_ prefix).
 * This module must never be imported from client components.
 */

export class FlaskError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "FlaskError";
  }
}

function getFlaskUrl(): string {
  const url = process.env.FLASK_URL;
  if (!url) {
    throw new Error("FLASK_URL environment variable is not set. This is a server-only variable.");
  }
  return url.replace(/\/$/, ""); // strip trailing slash
}

/**
 * Fetch a path from the Flask backend, forwarding optional search params.
 * Always uses cache: 'no-store' to ensure fresh data on every request.
 *
 * Does NOT throw on non-2xx — callers decide how to handle status codes.
 * Use flaskFetch when you need the raw Response (e.g. in route handlers).
 */
export async function flaskFetch(
  path: string,
  searchParams?: URLSearchParams,
): Promise<Response> {
  const base = getFlaskUrl();
  const url = searchParams?.toString()
    ? `${base}${path}?${searchParams.toString()}`
    : `${base}${path}`;

  return fetch(url, { cache: "no-store" });
}

/**
 * Authenticated Flask helpers (Auth mechanism A2).
 *
 * These helpers attach the short-lived internal HS256 JWT as an
 * Authorization: Bearer header so Flask @require_auth can validate it.
 * Always use cache: 'no-store' to prevent stale auth state.
 *
 * The `token` parameter is the signed HS256 string returned by mintInternalToken().
 */

export async function flaskAuthGet(path: string, token: string): Promise<Response> {
  const base = getFlaskUrl();
  return fetch(`${base}${path}`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });
}

export async function flaskAuthPost(
  path: string,
  token: string,
  body?: unknown,
): Promise<Response> {
  const base = getFlaskUrl();
  return fetch(`${base}${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    cache: "no-store",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export async function flaskAuthPatch(
  path: string,
  token: string,
  body?: unknown,
): Promise<Response> {
  const base = getFlaskUrl();
  return fetch(`${base}${path}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    cache: "no-store",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export async function flaskAuthDelete(path: string, token: string): Promise<Response> {
  const base = getFlaskUrl();
  return fetch(`${base}${path}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });
}

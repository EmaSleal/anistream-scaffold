/**
 * Vitest tests for ingestSeries() in ingest.ts (ADR-014): non-JSON or non-ok
 * Flask responses must surface as a readable Error, not a JSON parse failure.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/auth", () => ({
  auth: vi.fn().mockResolvedValue({ user: { role: "ADMIN" } }),
}));

vi.mock("@/lib/flask-client", () => ({ flaskFetch: vi.fn() }));

import { ingestSeries } from "./ingest";

function stubFetch(res: Partial<Response> & { json?: () => Promise<unknown>; text?: () => Promise<string> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res));
}

describe("ingestSeries", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns the parsed body on ok JSON", async () => {
    const body = { series_id: "naruto", series_title: "Naruto", episodes_ingested: 3 };
    stubFetch({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(body),
      json: async () => body,
    });
    await expect(ingestSeries(21)).resolves.toEqual(body);
  });

  it("throws a readable error with the status when the response is HTML", async () => {
    stubFetch({
      ok: false,
      status: 502,
      text: async () => "<html><body>502 Bad Gateway</body></html>",
      json: async () => {
        throw new SyntaxError("Unexpected token <");
      },
    });
    await expect(ingestSeries(21)).rejects.toThrow(
      "Ingest failed (502): upstream timeout or non-JSON response"
    );
  });

  it("throws the same readable error for an HTML body on a 200", async () => {
    stubFetch({
      ok: true,
      status: 200,
      text: async () => "<html>oops</html>",
      json: async () => {
        throw new SyntaxError("Unexpected token <");
      },
    });
    await expect(ingestSeries(21)).rejects.toThrow(/Ingest failed \(200\)/);
  });

  it("includes the server error message and status on non-ok JSON", async () => {
    const body = { error: "Anime not found on MAL" };
    stubFetch({
      ok: false,
      status: 404,
      text: async () => JSON.stringify(body),
      json: async () => body,
    });
    await expect(ingestSeries(21)).rejects.toThrow("Ingest failed (404): Anime not found on MAL");
  });
});

/**
 * Vitest tests for ingestSeries() in ingest.ts (ADR-014): non-JSON or non-ok
 * Flask responses must surface as a readable Error, not a JSON parse failure.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/auth", () => ({
  auth: vi.fn().mockResolvedValue({ user: { role: "ADMIN" } }),
}));

vi.mock("@/lib/flask-client", () => ({ flaskFetch: vi.fn() }));
vi.mock("@/lib/internal-token", () => ({
  mintInternalToken: vi.fn().mockResolvedValue("minted-admin-token"),
}));

import { auth } from "@/auth";
import { ingestSeries, ingestSeriesAsAdmin, ingestFranchiseMember } from "./ingest";

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

describe("ingestFranchiseMember", () => {
  const input = { mal_id: 301, franchise_id: "300", season_order: 2, relation: "Sequel", title: "S2" };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("posts the member body to /api/ingest/member and returns the parsed result", async () => {
    const body = { mal_id: 301, status: "ok", episodes_ingested: 12, principal_slug: "s2" };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(body),
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(ingestFranchiseMember(input)).resolves.toEqual(body);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/ingest\/member$/);
    expect(JSON.parse(init.body as string)).toEqual(input);
  });

  it("throws a readable error on an HTML response", async () => {
    stubFetch({ ok: false, status: 504, text: async () => "<html>timeout</html>" });
    await expect(ingestFranchiseMember(input)).rejects.toThrow(
      "Ingest failed (504): upstream timeout or non-JSON response"
    );
  });

  it("surfaces the server error message on a 400", async () => {
    stubFetch({ ok: false, status: 400, text: async () => JSON.stringify({ error: "mal_id must be a positive integer" }) });
    await expect(ingestFranchiseMember(input)).rejects.toThrow(
      "Ingest failed (400): mal_id must be a positive integer"
    );
  });

  it("rejects non-admin callers without calling Flask", async () => {
    vi.mocked(auth).mockResolvedValueOnce({ user: { role: "USER" } } as never);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(ingestFranchiseMember(input)).rejects.toThrow("Unauthorized");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("slug origin (ADR-016)", () => {
  const okRes = {
    ok: true,
    status: 200,
    text: async () => "{}",
    json: async () => ({}),
  };

  function lastCall() {
    const [, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    return { headers: init.headers as Record<string, string>, body: JSON.parse(init.body) };
  }

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(auth).mockResolvedValue({ user: { role: "ADMIN", email: "a@b.c" } } as never);
    stubFetch(okRes);
  });

  it("admin action sends slug_source=admin and the internal admin token", async () => {
    await ingestSeriesAsAdmin(21, "jk", "av1");
    const { headers, body } = lastCall();
    expect(headers.Authorization).toBe("Bearer minted-admin-token");
    expect(body).toMatchObject({ mal_id: 21, fallback_slug: "jk", animeav1_slug: "av1", slug_source: "admin" });
  });

  it("ingestSeries (IngestTrigger path) sends neither marker nor token", async () => {
    await ingestSeries(21, undefined, "own-canonical-slug");
    const { headers, body } = lastCall();
    expect(headers.Authorization).toBeUndefined();
    expect(body).not.toHaveProperty("slug_source");
    expect(body.animeav1_slug).toBe("own-canonical-slug");
  });

  it("member ingest sends no marker or token", async () => {
    await ingestFranchiseMember({ mal_id: 1, franchise_id: "f", season_order: 1, relation: "Sequel" });
    const { headers, body } = lastCall();
    expect(headers.Authorization).toBeUndefined();
    expect(body).not.toHaveProperty("slug_source");
  });
});

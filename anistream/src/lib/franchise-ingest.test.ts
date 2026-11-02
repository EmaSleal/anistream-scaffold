import { describe, it, expect, vi } from "vitest";
import {
  runFranchiseMembers,
  summarize,
  type MemberCall,
  type MemberState,
  type MemberToIngest,
} from "./franchise-ingest";

const members: MemberToIngest[] = [
  { mal_id: 1, title: "A", relation: "Sequel", season_order: 2 },
  { mal_id: 2, title: "B", relation: "Sequel", season_order: 3 },
  { mal_id: 3, title: "C", relation: "Side story", season_order: 4 },
];

function collect() {
  const states = new Map<number, MemberState>();
  const history: Array<[number, string]> = [];
  return {
    states,
    history,
    onUpdate: (id: number, s: MemberState) => {
      states.set(id, s);
      history.push([id, s.status]);
    },
  };
}

describe("runFranchiseMembers", () => {
  it("runs members sequentially and sends franchise_id/order/relation", async () => {
    const calls: number[] = [];
    let active = 0;
    const ingestMember: MemberCall = vi.fn(async (input) => {
      active++;
      expect(active).toBe(1);
      calls.push(input.mal_id);
      await Promise.resolve();
      active--;
      return { status: "ok", episodes_ingested: 12 };
    });
    const { onUpdate, states } = collect();
    const summary = await runFranchiseMembers({ members, franchiseId: "F", ingestMember, onUpdate });

    expect(calls).toEqual([1, 2, 3]);
    expect(ingestMember).toHaveBeenNthCalledWith(1, {
      mal_id: 1, franchise_id: "F", season_order: 2, relation: "Sequel", title: "A",
    });
    expect(summary).toEqual({ total: 3, ok: 3, already_scraped: 0, error: 0, pending: 0 });
    expect(states.get(1)).toEqual({ status: "ok", episodes_ingested: 12 });
  });

  it("continues after a thrown error and after an error status", async () => {
    const ingestMember: MemberCall = vi
      .fn()
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce({ status: "error: db down", episodes_ingested: 0 })
      .mockResolvedValueOnce({ status: "already_scraped", episodes_ingested: 5 });
    const { onUpdate, states } = collect();
    const summary = await runFranchiseMembers({ members, franchiseId: "F", ingestMember, onUpdate });

    expect(ingestMember).toHaveBeenCalledTimes(3);
    expect(states.get(1)).toEqual({ status: "error", detail: "boom" });
    expect(states.get(2)?.status).toBe("error");
    expect(states.get(2)?.detail).toBe("error: db down");
    expect(states.get(3)?.status).toBe("already_scraped");
    expect(summary).toEqual({ total: 3, ok: 0, already_scraped: 1, error: 2, pending: 0 });
  });

  it("maps non-ok Flask statuses such as jikan_not_found to error with the raw status", async () => {
    const ingestMember: MemberCall = vi.fn().mockResolvedValue({ status: "jikan_not_found", episodes_ingested: 0 });
    const { onUpdate, states } = collect();
    await runFranchiseMembers({ members: [members[0]], franchiseId: "F", ingestMember, onUpdate });
    expect(states.get(1)).toMatchObject({ status: "error", detail: "jikan_not_found" });
  });

  it("resume skips ok and already_scraped members and retries the rest", async () => {
    const previous = new Map<number, MemberState>([
      [1, { status: "ok", episodes_ingested: 12 }],
      [2, { status: "error", detail: "boom" }],
      [3, { status: "already_scraped" }],
    ]);
    const ingestMember: MemberCall = vi.fn().mockResolvedValue({ status: "ok", episodes_ingested: 8 });
    const { onUpdate, history } = collect();
    const summary = await runFranchiseMembers({
      members, franchiseId: "F", ingestMember, onUpdate, previous,
    });

    expect(ingestMember).toHaveBeenCalledTimes(1);
    expect(ingestMember).toHaveBeenCalledWith(expect.objectContaining({ mal_id: 2 }));
    expect(history.filter(([id]) => id !== 2)).toEqual([]);
    expect(summary).toEqual({ total: 3, ok: 2, already_scraped: 1, error: 0, pending: 0 });
  });

  it("emits pending for all, then running then final per member", async () => {
    const ingestMember: MemberCall = vi.fn().mockResolvedValue({ status: "ok", episodes_ingested: 1 });
    const { onUpdate, history } = collect();
    await runFranchiseMembers({ members: members.slice(0, 2), franchiseId: "F", ingestMember, onUpdate });
    expect(history).toEqual([
      [1, "pending"], [2, "pending"],
      [1, "running"], [1, "ok"],
      [2, "running"], [2, "ok"],
    ]);
  });
});

describe("summarize", () => {
  it("counts missing states as pending", () => {
    const states = new Map<number, MemberState>([[1, { status: "ok" }]]);
    expect(summarize(members, states)).toEqual({
      total: 3, ok: 1, already_scraped: 0, error: 0, pending: 2,
    });
  });
});

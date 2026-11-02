"use client";

import { useCallback, useRef, useState } from "react";
import {
  ingestSeries,
  ingestFranchiseMember,
  type IngestResult,
} from "@/app/actions/ingest";
import {
  runFranchiseMembers,
  summarize,
  type FranchiseSummary,
  type MemberState,
  type MemberToIngest,
} from "@/lib/franchise-ingest";

/**
 * Admin ingest flow (ADR-015): main series first, then each franchise member
 * sequentially. `resume` re-runs only the members that are not yet done.
 */
export function useFranchiseIngest() {
  const [members, setMembers] = useState<MemberToIngest[]>([]);
  const [states, setStates] = useState<Map<number, MemberState>>(new Map());
  const [summary, setSummary] = useState<FranchiseSummary | null>(null);
  const [running, setRunning] = useState(false);
  const [main, setMain] = useState<IngestResult | null>(null);
  const franchiseIdRef = useRef<string | null>(null);
  const statesRef = useRef<Map<number, MemberState>>(new Map());

  const runMembers = useCallback(async (list: MemberToIngest[], franchiseId: string) => {
    setRunning(true);
    setSummary(null);
    try {
      const result = await runFranchiseMembers({
        members: list,
        franchiseId,
        ingestMember: ingestFranchiseMember,
        previous: statesRef.current,
        onUpdate: (malId, state) => {
          statesRef.current = new Map(statesRef.current).set(malId, state);
          setStates(statesRef.current);
        },
      });
      setSummary(result);
    } finally {
      setRunning(false);
    }
  }, []);

  /** Runs the main ingest, then the members. Throws if the main ingest fails. */
  const start = useCallback(
    async (malId: number, fallbackSlug?: string, animeav1Slug?: string): Promise<IngestResult> => {
      setRunning(true);
      setMembers([]);
      setMain(null);
      setSummary(null);
      statesRef.current = new Map();
      setStates(statesRef.current);
      let main: IngestResult;
      try {
        main = await ingestSeries(malId, fallbackSlug, animeav1Slug);
      } catch (err) {
        setRunning(false);
        throw err;
      }
      setMain(main);
      const list: MemberToIngest[] = (main.franchise_members ?? []).map((m) => ({
        mal_id: m.mal_id,
        title: m.title,
        relation: m.relation,
        season_order: m.season_order,
      }));
      franchiseIdRef.current = main.franchise_id;
      setMembers(list);
      await runMembers(list, main.franchise_id);
      return main;
    },
    [runMembers]
  );

  const resume = useCallback(async () => {
    if (!franchiseIdRef.current) return;
    await runMembers(members, franchiseIdRef.current);
  }, [members, runMembers]);

  const live = summary ?? summarize(members, states);
  const canResume = !running && members.length > 0 && live.ok + live.already_scraped < members.length;

  return { main, members, states, summary: live, finished: summary !== null, running, canResume, start, resume };
}

export type FranchiseIngestController = ReturnType<typeof useFranchiseIngest>;

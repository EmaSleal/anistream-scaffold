/**
 * Sequential franchise-member ingest driver (ADR-015). Framework-free so it can
 * be unit-tested: the caller injects the member action and an update callback.
 */

export type MemberStatus = "pending" | "running" | "ok" | "already_scraped" | "error";

export interface MemberToIngest {
  mal_id: number;
  title: string;
  relation: string;
  season_order: number;
}

export interface MemberState {
  status: MemberStatus;
  /** Raw Flask status / error message, shown next to non-ok results. */
  detail?: string;
  episodes_ingested?: number;
}

export interface MemberCallResult {
  status: string;
  episodes_ingested: number;
}

export type MemberCall = (input: {
  mal_id: number;
  franchise_id: string;
  season_order: number;
  relation: string;
  title: string;
}) => Promise<MemberCallResult>;

export interface FranchiseSummary {
  total: number;
  ok: number;
  already_scraped: number;
  error: number;
  pending: number;
}

export function isDone(state: MemberState | undefined): boolean {
  return state?.status === "ok" || state?.status === "already_scraped";
}

export function summarize(
  members: MemberToIngest[],
  states: ReadonlyMap<number, MemberState>
): FranchiseSummary {
  const summary: FranchiseSummary = {
    total: members.length,
    ok: 0,
    already_scraped: 0,
    error: 0,
    pending: 0,
  };
  for (const m of members) {
    const status = states.get(m.mal_id)?.status ?? "pending";
    if (status === "ok") summary.ok++;
    else if (status === "already_scraped") summary.already_scraped++;
    else if (status === "error") summary.error++;
    else summary.pending++;
  }
  return summary;
}

function toState(result: MemberCallResult): MemberState {
  const { status, episodes_ingested } = result;
  if (status === "ok" || status === "already_scraped") {
    return { status, episodes_ingested };
  }
  // Any other Flask status (jikan_not_found, normalize_failed, "error: ...").
  return { status: "error", detail: status, episodes_ingested };
}

/**
 * Ingests members one at a time. A failed member (thrown error or non-ok
 * status) never stops the rest. With `previous`, members already ok or
 * already_scraped are skipped (resume) and keep their previous state.
 */
export async function runFranchiseMembers(opts: {
  members: MemberToIngest[];
  franchiseId: string;
  ingestMember: MemberCall;
  onUpdate: (malId: number, state: MemberState) => void;
  previous?: ReadonlyMap<number, MemberState>;
}): Promise<FranchiseSummary> {
  const { members, franchiseId, ingestMember, onUpdate, previous } = opts;
  const finalStates = new Map<number, MemberState>();

  for (const m of members) {
    const prior = previous?.get(m.mal_id);
    if (prior && isDone(prior)) {
      finalStates.set(m.mal_id, prior);
      continue;
    }
    onUpdate(m.mal_id, { status: "pending" });
  }

  for (const m of members) {
    if (finalStates.has(m.mal_id)) continue;
    onUpdate(m.mal_id, { status: "running" });
    let state: MemberState;
    try {
      state = toState(
        await ingestMember({
          mal_id: m.mal_id,
          franchise_id: franchiseId,
          season_order: m.season_order,
          relation: m.relation,
          title: m.title,
        })
      );
    } catch (err) {
      state = { status: "error", detail: err instanceof Error ? err.message : "Unknown error" };
    }
    finalStates.set(m.mal_id, state);
    onUpdate(m.mal_id, state);
  }

  return summarize(members, finalStates);
}

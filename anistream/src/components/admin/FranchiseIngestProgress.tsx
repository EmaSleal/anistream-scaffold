"use client";

import type { FranchiseIngestController } from "@/hooks/useFranchiseIngest";
import styles from "./FranchiseIngestProgress.module.css";

const LABELS = {
  pending: "pending",
  running: "running",
  ok: "ok",
  already_scraped: "already_scraped",
  error: "error",
} as const;

export default function FranchiseIngestProgress({
  controller,
}: {
  controller: FranchiseIngestController;
}) {
  const { members, states, summary, finished, running, canResume, resume } = controller;
  if (members.length === 0) return null;

  return (
    <div className={styles.wrap}>
      <p className={styles.heading}>Franchise members ({members.length})</p>
      <ul className={styles.list}>
        {members.map((m) => {
          const state = states.get(m.mal_id);
          const status = state?.status ?? "pending";
          return (
            <li key={m.mal_id} className={styles.item}>
              <span className={`${styles.badge} ${styles[status]}`}>{LABELS[status]}</span>
              <span className={styles.title}>{m.title || `MAL ${m.mal_id}`}</span>
              <span className={styles.meta}>
                {m.relation} · #{m.season_order}
              </span>
              {state?.detail && <span className={styles.detail}>{state.detail}</span>}
            </li>
          );
        })}
      </ul>
      {finished && (
        <p className={styles.summary}>
          Summary: {summary.ok} ok, {summary.already_scraped} already scraped, {summary.error} failed
          {summary.pending > 0 ? `, ${summary.pending} pending` : ""}
        </p>
      )}
      {canResume && (
        <button type="button" className={styles.resumeBtn} onClick={() => void resume()} disabled={running}>
          Resume
        </button>
      )}
    </div>
  );
}

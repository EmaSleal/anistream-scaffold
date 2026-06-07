import Link from "next/link";
import type { Series } from "@/types";
import styles from "./FranchiseSection.module.css";

interface Props {
  members: Series[];
  currentId: string;
  targetId: string | null;
}

export function FranchiseSection({ members, currentId, targetId }: Props) {
  const sorted = [...members].sort((a, b) => (a.seasonOrder ?? 0) - (b.seasonOrder ?? 0));

  return (
    <div className={styles.section}>
      <h3 className={styles.heading}>More in this franchise</h3>
      <div className={styles.list}>
        {sorted.map((member) => {
          const isCurrent = member.id === currentId;
          const isTarget = member.id === targetId;

          return (
            <Link
              key={member.id}
              href={`/series/${member.id}`}
              className={`${styles.chip} ${isCurrent ? styles.chipActive : ""}`}
            >
              {isTarget && !isCurrent && (
                <span className={styles.playIcon}>▶</span>
              )}
              {member.title}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

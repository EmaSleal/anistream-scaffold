export const dynamic = "force-dynamic";

import Image from "next/image";
import type { Metadata } from "next";
import { auth, signOut } from "@/auth";
import { getWatchlistIds } from "@/app/actions/watchlist";
import styles from "./account.module.css";

export const metadata: Metadata = { title: "Account", robots: { index: false, follow: false } };

export default async function AccountPage() {
  const [session, watchlistIds] = await Promise.all([
    auth(),
    getWatchlistIds(),
  ]);

  const user = session?.user;

  return (
    <div className={styles.page}>
      <div className={`card ${styles.cardCentered}`}>
        <div className={styles.avatarWrap}>
          {user?.image ? (
            <Image
              src={user.image}
              alt={user.name ?? "User avatar"}
              width={96}
              height={96}
              className={styles.avatar}
            />
          ) : (
            <div className={styles.avatarFallback}>
              {(user?.name ?? "U")[0].toUpperCase()}
            </div>
          )}
        </div>

        <div className={styles.info}>
          <h1 className={styles.name}>{user?.name ?? "—"}</h1>
          <p className={styles.email}>{user?.email ?? "—"}</p>
        </div>

        <div className={styles.stats}>
          <div className={styles.stat}>
            <span className={styles.statValue}>{watchlistIds.length}</span>
            <span className="label-caps">In Watchlist</span>
          </div>
        </div>

        <form
          action={async () => {
            "use server";
            await signOut({ redirectTo: "/" });
          }}
        >
          <button type="submit" className={styles.logoutBtn}>
            Sign out
          </button>
        </form>
      </div>
    </div>
  );
}

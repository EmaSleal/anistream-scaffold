"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import { useScrollHide } from "@/hooks/useScrollHide";
import { cn } from "@/lib/utils";
import styles from "./Navbar.module.css";

const NAV_ITEMS = [
  { label: "Home",       href: "/" },
  { label: "My Lists",   href: "/my-lists" },
  { label: "Browse",     href: "/browse" },
  { label: "Simulcasts", href: "/browse?filter=simulcast" },
  { label: "Account",    href: "/account" },
] as const;

export function Navbar() {
  const pathname = usePathname();
  const isScrolled = useScrollHide(40);
  const { data: session } = useSession();

  return (
    <header className={cn(styles.header, isScrolled && styles.scrolled)}>
      <nav className={styles.nav} aria-label="Main navigation">
        <Link href="/" className={styles.logo} aria-label="Anistream home">
          <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
            <circle cx="14" cy="14" r="14" fill="#F47521" />
            <circle cx="14" cy="14" r="7" fill="none" stroke="white" strokeWidth="3" />
            <circle cx="14" cy="14" r="3" fill="white" />
          </svg>
          <span className={styles.logoText}>anistream</span>
        </Link>

        <ul className={styles.navList}>
          {NAV_ITEMS.map(({ label, href }) => (
            <li key={href}>
              <Link
                href={href}
                className={cn(
                  styles.navItem,
                  pathname === href && styles.active
                )}
              >
                {label}
              </Link>
            </li>
          ))}
          {session?.user?.role === "ADMIN" && (
            <li>
              <Link
                href="/admin"
                className={cn(styles.navItem, styles.adminItem, pathname === "/admin" && styles.active)}
              >
                Admin
              </Link>
            </li>
          )}
        </ul>

        <div className={styles.actions}>
          <button className={styles.iconBtn} aria-label="Search">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
            </svg>
          </button>
          <button className={styles.iconBtn} aria-label="Watchlist">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z" />
            </svg>
          </button>
          <Link
            href="/account"
            className={styles.avatar}
            aria-label="Account"
            title={session?.user?.name ?? "Account"}
          >
            {session?.user?.image ? (
              <Image
                src={session.user.image}
                alt={session.user.name ?? "User avatar"}
                width={32}
                height={32}
                className={styles.avatarImg}
              />
            ) : (
              <span aria-hidden="true">
                {(session?.user?.name ?? "U")[0].toUpperCase()}
              </span>
            )}
          </Link>
        </div>
      </nav>
    </header>
  );
}

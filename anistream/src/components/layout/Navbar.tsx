"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import { signIn } from "next-auth/react";
import { useScrollHide } from "@/hooks/useScrollHide";
import { cn } from "@/lib/utils";
import styles from "./Navbar.module.css";

const NAV_ITEMS = [
  { label: "Home",       href: "/" },
  { label: "My Lists",   href: "/my-lists" },
  { label: "Browse",     href: "/browse" },
  { label: "Simulcasts", href: "/simulcast" },
  { label: "Account",    href: "/account" },
] as const;

const BOTTOM_NAV_ITEMS = [
  { label: "Home",       href: "/" },
  { label: "My Lists",   href: "/my-lists" },
  { label: "Browse",     href: "/browse" },
  { label: "Simulcasts", href: "/simulcast" },
] as const;

function NavIcon({ href }: { href: string }) {
  switch (href) {
    case "/":
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
          <polyline points="9 22 9 12 15 12 15 22" />
        </svg>
      );
    case "/my-lists":
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z" />
        </svg>
      );
    case "/browse":
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <circle cx="12" cy="12" r="10" />
          <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
        </svg>
      );
    case "/simulcast":
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <polygon points="5 3 19 12 5 21 5 3" />
        </svg>
      );
    default:
      return null;
  }
}

export function Navbar() {
  const pathname = usePathname();
  const isScrolled = useScrollHide(40);
  const { data: session, status } = useSession();

  return (
    <>
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

        {status !== "unauthenticated" && (
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
                  href="/admin/simulcast"
                  className={cn(styles.navItem, styles.adminItem, pathname === "/admin/simulcast" && styles.active)}
                >
                  Admin
                </Link>
              </li>
            )}
          </ul>
        )}

        <div className={styles.actions}>
          {status !== "unauthenticated" && (
            <>
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
            </>
          )}
          {status === "unauthenticated" ? (
            <button
              className={styles.signInBtn}
              onClick={() => signIn("google")}
              type="button"
            >
              Sign In
            </button>
          ) : (
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
          )}
        </div>
      </nav>
    </header>

    {status !== "unauthenticated" && (
      <nav className={styles.bottomNav} aria-label="Mobile navigation">
        {BOTTOM_NAV_ITEMS.map(({ label, href }) => (
          <Link
            key={href}
            href={href}
            className={cn(styles.bottomNavItem, pathname === href && styles.bottomNavActive)}
          >
            <NavIcon href={href} />
            <span>{label}</span>
          </Link>
        ))}
      </nav>
    )}
    </>
  );
}

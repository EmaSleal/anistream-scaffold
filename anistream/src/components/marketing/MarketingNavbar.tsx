"use client";

import Link from "next/link";
import { signIn } from "next-auth/react";
import { useScrollHide } from "@/hooks/useScrollHide";
import { cn } from "@/lib/utils";
import styles from "./MarketingNavbar.module.css";

export function MarketingNavbar() {
  const isScrolled = useScrollHide(40);

  return (
    <header className={cn(styles.header, isScrolled && styles.scrolled)}>
      <nav className={styles.nav} aria-label="Marketing navigation">
        <Link href="/" className={styles.logo} aria-label="Anistream home">
          <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
            <circle cx="14" cy="14" r="14" fill="#F47521" />
            <circle cx="14" cy="14" r="7" fill="none" stroke="white" strokeWidth="3" />
            <circle cx="14" cy="14" r="3" fill="white" />
          </svg>
          <span className={styles.logoText}>anistream</span>
        </Link>

        <ul className={styles.navLinks} aria-label="Page sections">
          <li><a href="#features" className={styles.navLink}>Features</a></li>
          <li><a href="#catalog" className={styles.navLink}>Catalog</a></li>
          <li><a href="#faq" className={styles.navLink}>FAQ</a></li>
        </ul>

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.signInBtn}
            onClick={() => signIn("google")}
          >
            Sign In
          </button>
        </div>
      </nav>
    </header>
  );
}

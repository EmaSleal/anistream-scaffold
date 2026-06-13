"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./AdminNav.module.css";

const LINKS = [
  { href: "/admin", label: "Ingest" },
  { href: "/admin/simulcast", label: "Simulcast" },
  { href: "/admin/browse", label: "Browse" },
] as const;

export function AdminNav() {
  const pathname = usePathname();
  return (
    <nav className={styles.nav}>
      {LINKS.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          className={`${styles.link} ${pathname === href ? styles.active : ""}`}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}

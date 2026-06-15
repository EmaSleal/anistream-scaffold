import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { auth } from "@/auth";
import BrowseTable from "@/components/admin/BrowseTable";
import { AdminNav } from "@/components/admin/AdminNav";
import styles from "../admin.module.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Browse Catalog", robots: { index: false, follow: false } };

export default async function BrowsePage() {
  const session = await auth();

  if (!session) redirect("/login");

  if (session.user.role !== "ADMIN") {
    return (
      <div className="page-content">
        <div className={`card ${styles.cardAdmin}`}>
          <h1 className={styles.title}>Access denied</h1>
          <p className={styles.subtitle}>This page is restricted to admins.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-content">
      <AdminNav />
      <BrowseTable />
    </div>
  );
}

import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { auth } from "@/auth";
import { getSimulcastSeries, getUnresolvedGaps } from "@/app/actions/simulcast-admin";
import SimulcastTable from "@/components/admin/SimulcastTable";
import { AdminNav } from "@/components/admin/AdminNav";
import styles from "../admin.module.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Simulcast Manager", robots: { index: false, follow: false } };

export default async function SimulcastPage() {
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

  const series = await getSimulcastSeries();

  // Read-only visibility section (simulcast-gap-recovery Phase 4). Fails
  // open to an empty list so a transient error here never blocks the main
  // Simulcast Manager table the admin already relies on daily.
  const unresolvedGaps = await getUnresolvedGaps().catch(() => []);

  return (
    <div className="page-content">
      <AdminNav />
      <SimulcastTable series={series} unresolvedGaps={unresolvedGaps} />
    </div>
  );
}

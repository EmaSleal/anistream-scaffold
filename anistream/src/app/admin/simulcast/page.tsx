import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { auth } from "@/auth";
import { getSimulcastSeries } from "@/app/actions/simulcast-admin";
import SimulcastTable from "./SimulcastTable";
import styles from "../admin.module.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Simulcast Manager" };

export default async function SimulcastPage() {
  const session = await auth();

  if (!session) redirect("/login");

  if (session.user.role !== "ADMIN") {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <h1 className={styles.title}>Access denied</h1>
          <p className={styles.subtitle}>This page is restricted to admins.</p>
        </div>
      </div>
    );
  }

  const series = await getSimulcastSeries();

  return <SimulcastTable series={series} />;
}

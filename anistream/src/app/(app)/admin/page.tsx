import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { auth } from "@/auth";
import IngestForm from "@/components/admin/IngestForm";
import { AdminNav } from "@/components/admin/AdminNav";
import styles from "./admin.module.css";

export const metadata: Metadata = { title: "Admin", robots: { index: false, follow: false } };

interface AdminPageProps {
  searchParams: Promise<{ slug?: string }>;
}

export default async function AdminPage({ searchParams }: AdminPageProps) {
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

  const { slug } = await searchParams;

  return (
    <div className="page-content">
      <AdminNav />
      <div className={`card ${styles.cardAdmin}`}>
        <div className={styles.header}>
          <h1 className={styles.title}>Admin — Ingest Series</h1>
          <p className={styles.subtitle}>
            Links an existing series (by MAL ID) to its AnimeFlv source and pulls episodes.
          </p>
        </div>
        <IngestForm initialSlug={slug} />
      </div>
    </div>
  );
}

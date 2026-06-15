import type { Metadata } from "next";
import { getSeriesList } from "@/lib/series";
import { MarketingHero } from "@/components/marketing/MarketingHero";
import { TrustBar } from "@/components/marketing/TrustBar";
import { FeatureGrid } from "@/components/marketing/FeatureGrid";
import { CatalogRow } from "@/components/marketing/CatalogRow";
import { FAQSection } from "@/components/marketing/FAQSection";
import { LandingCTA } from "@/components/marketing/LandingCTA";
import styles from "./landing.module.css";

export const metadata: Metadata = {
  title: "Watch Anime Free — Anistream",
  description:
    "Watch the best anime free online. Simulcasts, sub & dub, thousands of titles. No subscription, no credit card required.",
  keywords: [
    "anime",
    "watch anime free",
    "anime streaming",
    "simulcast",
    "free anime",
    "sub",
    "dub",
  ],
  openGraph: {
    type: "website",
    title: "Watch Anime Free — Anistream",
    description:
      "Watch the best anime free online. Simulcasts, sub & dub, thousands of titles.",
    images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: "Anistream — Watch Anime Free" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Watch Anime Free — Anistream",
    description:
      "Watch the best anime free online. Simulcasts, sub & dub, thousands of titles.",
    images: ["/opengraph-image"],
  },
};

export const dynamic = "force-dynamic";

export default async function MarketingPage() {
  const allSeries = await getSeriesList({ limit: 1000, sort: "score" });

  const seriesCount = allSeries.length;
  const heroSeries = allSeries.filter((s) => s.bannerUrl).slice(0, 8);
  const catalogSeries = allSeries.slice(0, 20);

  return (
    <div className={styles.page}>
      {heroSeries.length > 0 && <MarketingHero series={heroSeries} />}
      <TrustBar seriesCount={seriesCount} />
      <FeatureGrid />
      <CatalogRow series={catalogSeries} />
      <FAQSection />
      <LandingCTA />
    </div>
  );
}

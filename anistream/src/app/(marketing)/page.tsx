import { getSeriesList } from "@/lib/series";
import { MarketingHero } from "@/components/marketing/MarketingHero";
import { TrustBar } from "@/components/marketing/TrustBar";
import { FeatureGrid } from "@/components/marketing/FeatureGrid";
import { CatalogRow } from "@/components/marketing/CatalogRow";
import { FAQSection } from "@/components/marketing/FAQSection";
import { LandingCTA } from "@/components/marketing/LandingCTA";
import styles from "./landing.module.css";

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

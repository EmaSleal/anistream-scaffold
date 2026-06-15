import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: "https://anistream.astro-solutions.net/",
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 1.0,
    },
    {
      url: "https://anistream.astro-solutions.net/login",
      lastModified: new Date(),
      changeFrequency: "yearly",
      priority: 0.3,
    },
  ];
}

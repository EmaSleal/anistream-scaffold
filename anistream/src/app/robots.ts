import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/login"],
        disallow: [
          "/home",
          "/browse",
          "/watch/",
          "/series/",
          "/simulcast",
          "/account",
          "/my-lists",
          "/admin/",
          "/api/",
        ],
      },
    ],
    sitemap: "https://anistream.astro-solutions.net/sitemap.xml",
  };
}

import type { MetadataRoute } from "next";
import { CANONICAL_SITE_URL } from "@/lib/brand";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/about", "/pricing", "/privacy", "/terms"],
        disallow: [
          "/account",
          "/chat",
          "/dashboard",
          "/datasets",
          "/history",
          "/login",
          "/onboarding",
          "/upload",
          "/api/",
        ],
      },
    ],
    sitemap: `${CANONICAL_SITE_URL}/sitemap.xml`,
    host: CANONICAL_SITE_URL,
  };
}

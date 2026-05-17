import type { MetadataRoute } from "next";
import {
  CANONICAL_SITE_URL,
  META_DESCRIPTION,
  PRODUCT_NAME,
  PRODUCT_TAGLINE,
} from "@/lib/brand";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: PRODUCT_NAME,
    short_name: PRODUCT_NAME,
    description: META_DESCRIPTION,
    start_url: CANONICAL_SITE_URL,
    scope: CANONICAL_SITE_URL,
    display: "standalone",
    background_color: "#f6f4ef",
    theme_color: "#4f46e5",
    categories: ["business", "productivity", "finance"],
    icons: [
      {
        src: "/snaptix-icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "maskable",
      },
    ],
    screenshots: [],
    shortcuts: [
      {
        name: "View pricing",
        short_name: "Pricing",
        description: PRODUCT_TAGLINE,
        url: `${CANONICAL_SITE_URL}/pricing`,
      },
    ],
  };
}

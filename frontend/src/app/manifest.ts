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
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
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

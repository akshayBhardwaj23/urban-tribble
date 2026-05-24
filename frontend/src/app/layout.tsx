import type { Metadata } from "next";
import { Geist_Mono, Inter, Fraunces } from "next/font/google";
import { GoogleAnalytics } from "@/components/google-analytics";
import { Providers } from "@/lib/providers";
import {
  CANONICAL_SITE_URL,
  META_DESCRIPTION,
  PRODUCT_NAME,
  SEO_KEYWORDS,
  SEO_TITLE,
} from "@/lib/brand";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL(CANONICAL_SITE_URL),
  applicationName: PRODUCT_NAME,
  title: {
    default: SEO_TITLE,
    template: `%s — ${PRODUCT_NAME}`,
  },
  description: META_DESCRIPTION,
  keywords: SEO_KEYWORDS,
  authors: [{ name: PRODUCT_NAME, url: CANONICAL_SITE_URL }],
  creator: PRODUCT_NAME,
  publisher: PRODUCT_NAME,
  category: "business software",
  alternates: {
    canonical: "/",
  },
  manifest: "/manifest.webmanifest",
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
  openGraph: {
    type: "website",
    siteName: PRODUCT_NAME,
    title: SEO_TITLE,
    description: META_DESCRIPTION,
    url: CANONICAL_SITE_URL,
    locale: "en_US",
    images: [
      {
        url: "/opengraph-image",
        width: 1200,
        height: 630,
        alt: `${PRODUCT_NAME} - AI business analyst for spreadsheets`,
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: SEO_TITLE,
    description: META_DESCRIPTION,
    images: ["/opengraph-image"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${geistMono.variable} ${fraunces.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <GoogleAnalytics />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

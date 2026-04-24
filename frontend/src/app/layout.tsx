import type { Metadata } from "next";
import { Geist_Mono, Inter, Fraunces } from "next/font/google";
import { Providers } from "@/lib/providers";
import { CANONICAL_SITE_URL, META_DESCRIPTION, PRODUCT_NAME } from "@/lib/brand";
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
  title: `${PRODUCT_NAME} — AI business analyst`,
  description: META_DESCRIPTION,
  openGraph: {
    type: "website",
    siteName: PRODUCT_NAME,
    title: `${PRODUCT_NAME} — AI business analyst`,
    description: META_DESCRIPTION,
    url: CANONICAL_SITE_URL,
  },
  twitter: {
    card: "summary_large_image",
    title: `${PRODUCT_NAME} — AI business analyst`,
    description: META_DESCRIPTION,
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
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

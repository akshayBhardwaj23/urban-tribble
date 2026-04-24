import type { Metadata } from "next";
import Link from "next/link";
import {
  CANONICAL_SITE_URL,
  PRODUCT_NAME,
} from "@/lib/brand";

export const metadata: Metadata = {
  title: `Terms — ${PRODUCT_NAME}`,
  description: `Terms of use for ${PRODUCT_NAME}.`,
};

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 dark:bg-slate-950 dark:text-slate-100">
      <main className="mx-auto max-w-2xl px-5 py-12 md:px-8 md:py-16">
        <p className="text-sm">
          <Link
            href="/"
            className="font-medium text-indigo-600 hover:underline dark:text-indigo-400"
          >
            ← {PRODUCT_NAME}
          </Link>
        </p>
        <h1 className="mt-8 text-3xl font-semibold tracking-tight text-slate-900 dark:text-white">
          Terms of use
        </h1>
        <p className="mt-4 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          Last updated: April 2026. These terms summarize rules for using {PRODUCT_NAME}{" "}
          at {CANONICAL_SITE_URL}. Replace or extend this page with counsel-approved terms
          before a broad public launch.
        </p>

        <section className="mt-10 space-y-4 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">
            The service
          </h2>
          <p>
            {PRODUCT_NAME} provides software to upload business spreadsheets, view
            dashboards, and obtain AI-assisted summaries and chat. Outputs are{" "}
            <strong className="text-slate-900 dark:text-white">informational</strong> and
            may be wrong; you are responsible for verifying figures against your original
            sources before decisions.
          </p>

          <h2 className="pt-6 text-base font-semibold text-slate-900 dark:text-white">
            Acceptable use
          </h2>
          <p>
            Do not use the service to break the law, attack systems, or upload content you
            do not have rights to use. We may suspend access for abuse or risk to the
            platform.
          </p>

          <h2 className="pt-6 text-base font-semibold text-slate-900 dark:text-white">
            Accounts and fees
          </h2>
          <p>
            Some features require a paid plan. Fees and renewal are as shown at checkout
            with our payment provider. You may cancel according to that provider’s flows.
          </p>

          <h2 className="pt-6 text-base font-semibold text-slate-900 dark:text-white">
            Disclaimer
          </h2>
          <p>
            The service is provided{" "}
            <strong className="text-slate-900 dark:text-white">as is</strong>. To the
            extent permitted by law, we disclaim warranties and limit liability arising
            from your use of AI-generated content or availability of the service.
          </p>
        </section>

        <p className="mt-12 text-xs text-slate-500 dark:text-slate-400">
          <Link href="/privacy" className="hover:underline">
            Privacy
          </Link>
        </p>
      </main>
    </div>
  );
}

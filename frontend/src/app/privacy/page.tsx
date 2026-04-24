import type { Metadata } from "next";
import Link from "next/link";
import {
  CANONICAL_SITE_URL,
  PRODUCT_NAME,
} from "@/lib/brand";

export const metadata: Metadata = {
  title: `Privacy — ${PRODUCT_NAME}`,
  description: `How ${PRODUCT_NAME} handles your data and account.`,
};

export default function PrivacyPage() {
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
          Privacy
        </h1>
        <p className="mt-4 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          Last updated: April 2026. This summary describes how {PRODUCT_NAME}{" "}
          ({CANONICAL_SITE_URL}) treats information you provide when using the service.
          It is not legal advice; consult counsel before launch if you need a full privacy
          policy for your jurisdiction.
        </p>

        <section className="mt-10 space-y-4 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">
            What we collect
          </h2>
          <ul className="list-disc space-y-2 pl-5">
            <li>
              <strong className="text-slate-900 dark:text-white">Account:</strong> email
              and name from your sign-in provider or email OTP flow.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">Workspace data:</strong>{" "}
              files you upload (e.g. spreadsheets), derived cleaned copies we store for
              charts and analysis, and metadata such as column types and row counts.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">AI usage:</strong> when
              you run a briefing, chat, or digest, relevant portions of your workspace
              summary or tables may be sent to our AI provider to generate text. Do not
              upload regulated or highly sensitive data unless your agreement with us
              allows it.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">Billing:</strong> if you
              subscribe, our payment provider (e.g. Razorpay) processes payment data under
              their terms.
            </li>
          </ul>

          <h2 className="pt-6 text-base font-semibold text-slate-900 dark:text-white">
            Retention and deletion
          </h2>
          <p>
            You can remove individual sources from a workspace in the app. To delete your
            entire account and workspaces, use{" "}
            <strong className="text-slate-900 dark:text-white">Account → Delete account</strong>{" "}
            while signed in. That removes your user record and owned workspace data from
            our application database and attempts to delete associated uploaded files from
            our servers. Backups or logs may persist for a limited time according to our
            hosting provider’s practices.
          </p>

          <h2 className="pt-6 text-base font-semibold text-slate-900 dark:text-white">
            Contact
          </h2>
          <p>
            For privacy requests, contact the team through the address shown on{" "}
            <Link href="/" className="text-indigo-600 hover:underline dark:text-indigo-400">
              {CANONICAL_SITE_URL}
            </Link>
            .
          </p>
        </section>

        <p className="mt-12 text-xs text-slate-500 dark:text-slate-400">
          <Link href="/terms" className="hover:underline">
            Terms of use
          </Link>
        </p>
      </main>
    </div>
  );
}

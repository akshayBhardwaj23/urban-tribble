import type { Metadata } from "next";
import Link from "next/link";
import {
  CANONICAL_SITE_URL,
  CONTACT_EMAIL,
  PRODUCT_NAME,
  contactMailto,
} from "@/lib/brand";

export const metadata: Metadata = {
  title: `Privacy - ${PRODUCT_NAME}`,
  description: `How ${PRODUCT_NAME} handles your data and account.`,
  alternates: {
    canonical: "/privacy",
  },
  openGraph: {
    title: `Privacy - ${PRODUCT_NAME}`,
    description: `How ${PRODUCT_NAME} handles your data and account.`,
    url: `${CANONICAL_SITE_URL}/privacy`,
  },
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
          Privacy Policy
        </h1>
        <p className="mt-4 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          Last updated: 1 September 2026. This policy describes how {PRODUCT_NAME}{" "}
          ({CANONICAL_SITE_URL}) collects, uses, stores, shares and protects information
          you provide when using the service, including data we receive from Google APIs.
        </p>

        <section className="mt-10 space-y-4 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">
            What we collect
          </h2>
          <ul className="list-disc space-y-2 pl-5">
            <li>
              <strong className="text-slate-900 dark:text-white">Account:</strong>{" "}
            email
              and name from your sign-in provider or email OTP flow.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">Workspace data:</strong>{" "}
              files you upload (e.g. spreadsheets), spreadsheets you choose to connect from
              a linked Google or Microsoft account, derived cleaned copies we store for
              charts and analysis, and metadata such as column types and row counts.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">
                Connected-source credentials:
              </strong>{" "}
              OAuth access and refresh tokens for accounts you connect, and any keys or
              connection strings you enter for other sources (e.g. a database or a Google
              service-account file).
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">AI usage:</strong>{" "}
            when
              you run a briefing, chat, or digest, relevant portions of your workspace
              summary or tables are sent to our AI provider to generate text. Do not
              upload regulated or highly sensitive data unless your agreement with us
              allows it.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">Billing:</strong>{" "}
            if you
              subscribe, our payment provider (Razorpay) processes payment data under
              their terms. We do not store card numbers.
            </li>
          </ul>

          <h2 className="pt-6 text-base font-semibold text-slate-900 dark:text-white">
            How we access and use Google user data
          </h2>
          <p>
            If you connect a Google account, {PRODUCT_NAME} requests only the scopes below
            and uses the data received from them only to deliver the features you asked
            for. We do not request or use Gmail, Calendar, Contacts, Photos or location
            data.
          </p>
          <ul className="list-disc space-y-2 pl-5">
            <li>
              <strong className="text-slate-900 dark:text-white">
                openid and email
              </strong>{" "}
              — we read your Google account&apos;s email address and user identifier, and
              use them solely to identify which Google account a connected source belongs
              to, to display it in the app, and to reconnect it when a token expires.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">
                Google Drive (drive.readonly)
              </strong>{" "}
              — we read your Drive file list in order to show you a browsable list of your
              spreadsheets (Google Sheets, .xlsx, .xls and .csv files) so you can pick
              which ones to import. Once you pick a file, we read the contents of{" "}
              <em>that file only</em> in order to import its rows into your workspace, and
              we re-read it when you or a scheduled sync refreshes that source. We do not
              read, index, download or analyse any other file in your Drive, and we never
              write to, modify or delete anything in your Drive.
            </li>
          </ul>
          <p>
            <strong className="text-slate-900 dark:text-white">
              What we store.
            </strong>{" "}
            For each source you import we store a derived copy of that spreadsheet&apos;s
            contents (a cleaned table plus metadata such as column names, types and row
            counts) in our application database and object storage, because that copy is
            what powers your dashboards, briefings and chat answers. We also store the
            Google OAuth refresh token for the connection so scheduled syncs can run
            without asking you to sign in again. We store no other Drive content.
          </p>
          <p>
            <strong className="text-slate-900 dark:text-white">
              What we do not do.
            </strong>{" "}
            We do not use Google user data for advertising or ad personalisation, we do not
            sell it, we do not use it to build advertising or credit profiles, and we do
            not use it to train, fine-tune or develop generalised AI or machine-learning
            models — ours or anyone else&apos;s. Our staff do not read your Google user
            data except with your explicit permission (for example when you ask us for
            support), where required for security purposes such as investigating abuse or
            a suspected incident, or to comply with applicable law.
          </p>
          <p>
            If you connect Google Analytics or BigQuery, you supply a Google service-account
            key yourself and we use it only to run the read-only queries needed to build the
            report or dataset you configured.
          </p>

          <h2 className="pt-6 text-base font-semibold text-slate-900 dark:text-white">
            Who we share, transfer or disclose data to
          </h2>
          <p>
            We do not sell your data or Google user data, and we do not share it with
            advertisers or data brokers. We share it only with the following service
            providers, only to the extent needed to run {PRODUCT_NAME}, and only under
            contracts that require them to protect it and to use it solely to provide
            their service to us:
          </p>
          <ul className="list-disc space-y-2 pl-5">
            <li>
              <strong className="text-slate-900 dark:text-white">
                OpenAI (AI processing):
              </strong>{" "}
              when you run a briefing, chat or digest, the relevant portions of your
              workspace data — which may include data imported from Google Sheets or
              Drive — are sent to OpenAI&apos;s API to generate the response. OpenAI
              processes this as our service provider under the OpenAI API terms and does
              not use API data to train its models.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">
                Cloud hosting and storage:
              </strong>{" "}
              our application servers, managed PostgreSQL database and S3-compatible
              object storage (Amazon S3 or Cloudflare R2), which hold your account record,
              imported datasets and encrypted credentials.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">
                Razorpay (payments):
              </strong>{" "}
              receives your billing details if you subscribe. Google user data is never
              sent to our payment provider.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">
                Email delivery:
              </strong>{" "}
              our transactional email provider sends sign-in codes and digests to your
              address.
            </li>
          </ul>
          <p>
            We may also disclose information if we are legally required to do so, or where
            necessary to investigate fraud, abuse or a security incident. If{" "}
            {PRODUCT_NAME} is ever involved in a merger or acquisition, we will give you
            notice before your data becomes subject to a different privacy policy. In every
            case, any transfer of information received from Google APIs remains subject to
            the Limited Use requirements described below.
          </p>

          <h2 className="pt-6 text-base font-semibold text-slate-900 dark:text-white">
            How we protect your data
          </h2>
          <ul className="list-disc space-y-2 pl-5">
            <li>
              <strong className="text-slate-900 dark:text-white">In transit:</strong>{" "}
            all
              traffic between your browser, our servers and Google&apos;s APIs is encrypted
              with HTTPS/TLS. The app is served over HTTPS only.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">At rest:</strong>{" "}
            our
              database and object storage are encrypted at rest by the hosting provider.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">
                Credentials and tokens:
              </strong>{" "}
              Google and Microsoft OAuth refresh tokens, service-account keys and any other
              connection secrets are additionally encrypted at the application layer with
              authenticated envelope encryption (AES-based Fernet) before they are written
              to the database, using keys held outside the database and rotatable without
              downtime. A database dump alone therefore does not expose your connected
              accounts. Tokens and secrets are never written to logs and are never sent to
              the browser.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">Access control:</strong>{" "}
              every dataset is scoped to the workspace that owns it and every API request
              is authenticated and authorised against that workspace, so one customer
              cannot read another&apos;s data. Administrative access to production systems
              is limited to staff who need it, is individually credentialed, and is used
              only for the purposes listed above.
            </li>
            <li>
              <strong className="text-slate-900 dark:text-white">Minimisation:</strong>{" "}
            we
              request read-only scopes, import only the files you select, and keep no copy
              of Drive content you have not imported.
            </li>
          </ul>
          <p>
            No system is perfectly secure, but if we become aware of a breach affecting
            your data we will notify you and any regulator as required by applicable law.
          </p>

          <h2 className="pt-6 text-base font-semibold text-slate-900 dark:text-white">
            Retention and deletion
          </h2>
          <p>
            We keep imported data for as long as the source exists in your workspace. You
            can remove an individual source at any time in the app; removing it deletes the
            stored copy of that spreadsheet&apos;s data and, for a connected source, the
            stored OAuth credentials for that connection.
          </p>
          <p>
            To delete your entire account and workspaces, use{" "}
            <strong className="text-slate-900 dark:text-white">
              Account → Delete account
            </strong>{" "}
            while signed in. That removes your user record, owned workspace data and stored
            connection credentials from our application database and deletes the associated
            uploaded and derived files from our storage. Backups and operational logs may
            persist for a limited period, typically no more than 30 days, before they age
            out.
          </p>
          <p>
            You can also revoke {PRODUCT_NAME}&apos;s access to your Google account at any
            time from{" "}
            <a
              href="https://myaccount.google.com/permissions"
              target="_blank"
              rel="noreferrer"
              className="text-indigo-600 hover:underline dark:text-indigo-400"
            >
              myaccount.google.com/permissions
            </a>
            . Revoking stops all further access to your Drive; to also delete data already
            imported, remove the source or delete your account as described above.
          </p>

          <h2 className="pt-6 text-base font-semibold text-slate-900 dark:text-white">
            Limited Use disclosure
          </h2>
          <p>
            {PRODUCT_NAME}&apos;s use and transfer of information received from Google APIs
            to any other app will adhere to the{" "}
            <a
              href="https://developers.google.com/terms/api-services-user-data-policy"
              target="_blank"
              rel="noreferrer"
              className="text-indigo-600 hover:underline dark:text-indigo-400"
            >
              Google API Services User Data Policy
            </a>
            , including the Limited Use requirements.
          </p>

          <h2 className="pt-6 text-base font-semibold text-slate-900 dark:text-white">
            Your rights
          </h2>
          <p>
            Depending on where you live, you may have the right to access, correct, export
            or delete your personal data, or to object to certain processing. You can
            export or delete most data yourself in the app; for anything else, email us at
            the address below and we will respond within the period required by applicable
            law.
          </p>

          <h2 className="pt-6 text-base font-semibold text-slate-900 dark:text-white">
            Changes to this policy
          </h2>
          <p>
            If we make a material change to how we handle your data, we will update the
            date at the top of this page and, where the change is significant, notify you
            in the app or by email.
          </p>

          <h2 className="pt-6 text-base font-semibold text-slate-900 dark:text-white">
            Contact
          </h2>
          <p>
            For privacy requests or questions about this policy, email{" "}
            <a
              href={contactMailto("Privacy request")}
              className="text-indigo-600 hover:underline dark:text-indigo-400"
            >
              {CONTACT_EMAIL}
            </a>
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

# Snaptix — Manual QA checklist (pre-release)

Use this document before sharing Snaptix with customers or pointing **snaptix.ai** at production.

**How to use each test case**

| Field             | Meaning                                                 |
| ----------------- | ------------------------------------------------------- |
| **ID**            | Reference for bugs (e.g. `TC-UP-003`)                   |
| **Priority**      | P0 = release blocker, P1 = should fix, P2 = nice to fix |
| **Pass criteria** | All bullets must be true to mark **Pass**               |

Record: **Tester**, **Date**, **Environment** (local / staging / prod), **Build/commit**, **Browser**.

---

## 0. Test environment setup

| #   | Step                                                                                          | Pass? |
| --- | --------------------------------------------------------------------------------------------- | ----- |
| 0.1 | Backend health: open `https://<api-host>/health` → `{"status":"ok"}` (or equivalent)          | ☐     |
| 0.2 | Frontend loads at your public URL (or `http://localhost:3000`)                                | ☐     |
| 0.3 | `DATABASE_URL` points to **Neon** (or stable Postgres), not expired Render Postgres           | ☐     |
| 0.4 | `UPLOAD_DIR` on Render uses a **persistent disk** path (if production); note path: ****\_**** | ☐     |
| 0.5 | `CORS_ORIGINS` includes your live frontend URL                                                | ☐     |
| 0.6 | `RESEND_API_KEY` + `RESEND_FROM_EMAIL` set (OTP sign-in)                                      | ☐     |
| 0.7 | Razorpay **test** keys + plan IDs match same mode (test/live)                                 | ☐     |
| 0.8 | Google OAuth redirect URIs include production callback URL                                    | ☐     |
| 0.9 | Demo files ready: `sample_data/slick-styles-demo/` (see section 1)                            | ☐     |

**Recommended test accounts**

| Account purpose | Suggestion                                                                                           |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| New user (Free) | Fresh email, never used before                                                                       |
| Paid test       | Razorpay **test mode** checkout → Starter or Pro                                                     |
| QA power user   | `AUTH_TEST_LOGIN_ENABLED=true` + fixed email in backend `.env` (skips OTP; gets **internal** limits) |

Use **separate browsers or profiles** for Free vs paid so sessions do not mix.

---

## 1. Demo data (Slick Styles)

Map files to **Import** templates on `/upload`:

| Template                | Folder                        | Suggested file(s)                                                                |
| ----------------------- | ----------------------------- | -------------------------------------------------------------------------------- |
| Monthly business review | `01-monthly-business-review/` | `monthly_revenue_and_profit_by_channel.xlsx`, `monthly_kpi_scorecard.xlsx`       |
| Profit leak audit       | `02-profit-leak-audit/`       | `product_margin_and_cogs_by_sku.xlsx`, `discounts_returns_and_chargebacks.xlsx`  |
| Sales performance       | `03-sales-performance/`       | `revenue_by_phone_model_and_case.xlsx`, `wholesale_sales_by_rep_and_region.xlsx` |
| Campaign efficiency     | `04-campaign-efficiency/`     | `paid_ads_campaign_performance.xlsx`                                             |
| Customer value          | `05-customer-value/`          | `customer_account_summary.xlsx`                                                  |

Also keep one **invalid** file for negative tests: empty `.xlsx`, wrong format (`.pdf`), or a tiny CSV with one row.

---

## 2. Marketing & public pages (unauthenticated)

### TC-PUB-001 — Landing page (P0)

| Step | Action                                           |
| ---- | ------------------------------------------------ |
| 1    | Open `/`                                         |
| 2    | Scroll hero, features, pricing teaser, footer    |
| 3    | Click **Pricing**, **Sign in** / **Get started** |

**Expected:** Page loads without console errors; links work; branding shows Snaptix; no auth required.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-PUB-002 — Pricing page (P0)

| Step | Action                                                   |
| ---- | -------------------------------------------------------- |
| 1    | Open `/pricing`                                          |
| 2    | Read Free / Starter / Pro cards and FAQ                  |
| 3    | Click plan CTAs while logged out → should route to login |

**Expected:** Copy matches plan limits (2 uploads on Free, etc.); FAQ expands; CTAs do not crash.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-PUB-003 — Legal pages (P1)

| Step | Action                                                 |
| ---- | ------------------------------------------------------ |
| 1    | Open `/privacy` and `/terms` from footer or direct URL |
| 2    | Return to home via link                                |

**Expected:** Pages render; links back to `/` work.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-PUB-004 — SEO / metadata (P2)

| Step | Action                                                       |
| ---- | ------------------------------------------------------------ |
| 1    | View page source on `/` — title and meta description present |
| 2    | Open `/robots.txt` and `/sitemap.xml` on deployed host       |

**Expected:** `snaptix.ai` canonical base; sitemap lists `/`, `/pricing`, `/privacy`, `/terms`.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

---

## 3. Authentication & onboarding

### TC-AUTH-001 — Email OTP sign-in (P0)

| Step | Action                                         |
| ---- | ---------------------------------------------- |
| 1    | Open `/login`                                  |
| 2    | Enter a real inbox you control → **Send code** |
| 3    | Enter OTP from email → verify                  |

**Expected:** Email arrives (check spam); valid code signs you in; invalid/expired code shows clear error.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-AUTH-002 — OTP resend cooldown (P1)

| Step | Action                                                                               |
| ---- | ------------------------------------------------------------------------------------ |
| 1    | Request code for an email                                                            |
| 2    | Within 60s, tap **Resend code** (on code step)                                       |
| 3    | Within 60s, tap **Use a different email**, re-enter the **same** email, submit again |

**Expected:** Steps 2–3 blocked or “wait N seconds”; no second email until cooldown ends. Cooldown is per email (a different address can request immediately). Backend returns 429; UI shows countdown on email and code steps.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-AUTH-003 — Google sign-in (P0 if you ship Google)

| Step | Action                                      |
| ---- | ------------------------------------------- |
| 1    | From `/login`, use **Continue with Google** |
| 2    | Complete OAuth                              |

**Expected:** Redirect back to app; session active; lands on onboarding or dashboard.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-AUTH-004 — Test login (P1, dev/staging only)

| Step | Action                                                                |
| ---- | --------------------------------------------------------------------- |
| 1    | With `AUTH_TEST_LOGIN_ENABLED=true`, sign in as configured test email |

**Expected:** No OTP required; reaches app; treated as internal/unlimited for QA.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-AUTH-005 — Onboarding — first workspace (P0)

| Step | Action                                                  |
| ---- | ------------------------------------------------------- |
| 1    | As **new** user with no workspaces, complete onboarding |
| 2    | Name workspace e.g. `Slick Styles Demo`                 |

**Expected:** Redirect to `/dashboard` or `/upload`; workspace appears in switcher.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-AUTH-006 — Session persistence (P0)

| Step | Action                                            |
| ---- | ------------------------------------------------- |
| 1    | Sign in → refresh browser → navigate `/dashboard` |
| 2    | Close tab, reopen site                            |

**Expected:** Still signed in (until session expires); not kicked to login unexpectedly.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-AUTH-007 — Sign out (P0)

| Step | Action                   |
| ---- | ------------------------ |
| 1    | Use user menu → sign out |

**Expected:** Session cleared; protected routes redirect to login.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

---

## 4. Workspaces

### TC-WS-001 — Workspace switcher (P0)

| Step | Action                                                       |
| ---- | ------------------------------------------------------------ |
| 1    | Create or use 2 workspaces (Pro plan, or internal test user) |
| 2    | Switch between them in sidebar                               |

**Expected:** Active workspace label updates; dashboard data changes per workspace (no cross-leak).

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-WS-002 — Free plan workspace cap (P1)

| Step | Action                                        |
| ---- | --------------------------------------------- |
| 1    | As **Free** user, try to create 2nd workspace |

**Expected:** Blocked with clear upgrade message; UI not broken.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-WS-003 — Pro multi-workspace (P1)

| Step | Action                                     |
| ---- | ------------------------------------------ |
| 1    | As **Pro** user, create up to 5 workspaces |

**Expected:** Allowed until cap; 6th blocked with message.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

---

## 5. Import / upload (all templates)

### TC-UP-001 — Template picker (P0)

| Step | Action                                                    |
| ---- | --------------------------------------------------------- |
| 1    | Go to `/upload`                                           |
| 2    | Confirm all 5 guided templates + **Manual upload** appear |
| 3    | Open one template → see recommended inputs                |

**Expected:** Icons/copy match template; back navigation works.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-UP-002 — Guided upload — Monthly business review (P0)

| Step | Action                                              |
| ---- | --------------------------------------------------- |
| 1    | Choose **Monthly business review**                  |
| 2    | Upload `monthly_revenue_and_profit_by_channel.xlsx` |
| 3    | Complete ingestion review (confirm columns/types)   |
| 4    | Finish import                                       |

**Expected:** Progress pipeline completes; source appears under **Sources**; no 500 errors.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-UP-003 — Guided upload — Profit leak audit (P0)

| Step | Action                                                                  |
| ---- | ----------------------------------------------------------------------- |
| 1    | Upload `product_margin_and_cogs_by_sku.xlsx` under Profit leak template |

**Expected:** Dataset created; margin-like columns detected.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-UP-004 — Guided upload — Sales performance (P1)

| Step | Action                                        |
| ---- | --------------------------------------------- |
| 1    | Upload `revenue_by_phone_model_and_case.xlsx` |

**Expected:** Success; rep/model/category fields usable later.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-UP-005 — Guided upload — Campaign efficiency (P1)

| Step | Action                                      |
| ---- | ------------------------------------------- |
| 1    | Upload `paid_ads_campaign_performance.xlsx` |

**Expected:** Success; spend/conversion style columns recognized.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-UP-006 — Guided upload — Customer value (P1)

| Step | Action                                 |
| ---- | -------------------------------------- |
| 1    | Upload `customer_account_summary.xlsx` |

**Expected:** Success; customer/tier columns recognized.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-UP-007 — Manual upload + context note (P0)

| Step | Action                                              |
| ---- | --------------------------------------------------- |
| 1    | Choose **Manual upload**                            |
| 2    | Add context e.g. `Q4 Slick Styles — Amazon returns` |
| 3    | Upload any valid xlsx/csv                           |

**Expected:** Context saved with source; ingestion flow same as guided.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-UP-008 — Multi-file queue (P1)

| Step | Action                              |
| ---- | ----------------------------------- |
| 1    | Drop 2–3 small files in one session |

**Expected:** Each processes or queues clearly; failures isolated per file.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-UP-009 — Invalid file (P0)

| Step | Action                             |
| ---- | ---------------------------------- |
| 1    | Upload `.pdf` or empty spreadsheet |

**Expected:** Clear error; app remains usable; no partial corrupt dataset.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-UP-010 — Free plan upload limit (P0)

| Step | Action                                                 |
| ---- | ------------------------------------------------------ |
| 1    | As **Free** user, upload until 2 lifetime uploads used |
| 2    | Attempt 3rd upload                                     |

**Expected:** Blocked with plan limit message + link to pricing.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

---

## 6. Sources (datasets list & detail)

### TC-SRC-001 — Sources list (P0)

| Step | Action                                                  |
| ---- | ------------------------------------------------------- |
| 1    | Open `/datasets`                                        |
| 2    | Confirm all imported sources listed with sensible names |

**Expected:** Row counts / dates visible; click opens detail.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-SRC-002 — Dataset detail — preview & columns (P0)

| Step | Action                            |
| ---- | --------------------------------- |
| 1    | Open a dataset from list          |
| 2    | View column roles / preview table |
| 3    | Change date filter if available   |

**Expected:** Data preview loads; filters affect charts/KPIs on same page.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-SRC-003 — Run dataset analysis (P0)

| Step | Action                                               |
| ---- | ---------------------------------------------------- |
| 1    | On dataset page, trigger **Run analysis** / briefing |
| 2    | Wait for completion                                  |

**Expected:** Briefing sections populate (priorities, insights, etc.); no infinite spinner.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-SRC-004 — Dataset forecast (P1)

| Step | Action                                             |
| ---- | -------------------------------------------------- |
| 1    | Run forecast on dataset with date + numeric column |

**Expected:** Chart renders; plausible series; error if insufficient history.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-SRC-005 — Append rows (P1)

| Step | Action                                                 |
| ---- | ------------------------------------------------------ |
| 1    | Use **Add rows** with compatible file (same structure) |

**Expected:** Row count increases; dashboards update.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-SRC-006 — Delete source (P0)

| Step | Action                                |
| ---- | ------------------------------------- |
| 1    | Delete a test source → confirm dialog |

**Expected:** Removed from list; overview no longer references it.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-SRC-007 — Missing file after redeploy (P1, staging)

| Step | Action                                                                  |
| ---- | ----------------------------------------------------------------------- |
| 1    | On staging **without** persistent disk: redeploy API → open old dataset |

**Expected:** User sees missing-file style error (validates your ops setup). _Skip if disk configured._

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

---

## 7. Overview dashboard (`/dashboard`)

### TC-DASH-001 — Overview with data (P0)

| Step | Action                                        |
| ---- | --------------------------------------------- |
| 1    | Open `/dashboard` with ≥1 source in workspace |
| 2    | Review KPI tiles and charts                   |

**Expected:** Charts render; no blank broken state; period toolbar works.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-DASH-002 — Period comparison (P1)

| Step | Action                                   |
| ---- | ---------------------------------------- |
| 1    | Change period (e.g. last month vs prior) |
| 2    | Use custom range if available            |

**Expected:** KPIs/charts update; no stale data from previous range.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-DASH-003 — Workspace AI briefing (P0)

| Step | Action                                             |
| ---- | -------------------------------------------------- |
| 1    | Run **workspace overview** / briefing on dashboard |
| 2    | Read priorities and trace/basis UI if shown        |

**Expected:** Coherent summary across sources; expand trace works.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-DASH-004 — Free vs paid briefing depth (P1)

| Step | Action                                                                   |
| ---- | ------------------------------------------------------------------------ |
| 1    | Compare briefing on **Free** vs **Starter/Pro** (fewer sections on Free) |

**Expected:** Free shows limited sections; paid fuller; upgrade nudge acceptable.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-DASH-005 — What changed (Starter+, P1)

| Step | Action                                                 |
| ---- | ------------------------------------------------------ |
| 1    | As paid user with history, view **What changed** block |

**Expected:** Visible on Starter+; empty/hidden on Free per plan.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-DASH-006 — Alerts (Pro only, P1)

| Step | Action                                      |
| ---- | ------------------------------------------- |
| 1    | As **Pro**, check alerts/signals section    |
| 2    | As **Free**, confirm not available or gated |

**Expected:** Matches plan matrix in `subscription_usage.py`.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-DASH-007 — Outlook forecast settings (P2)

| Step | Action                                             |
| ---- | -------------------------------------------------- |
| 1    | Configure workspace outlook forecast source column |
| 2    | Run outlook forecast                               |

**Expected:** Saves selection; forecast chart updates.

| Pass? | Notes                                |
| ----- | ------------------------------------ |
| ☐     | This has been removed from workspace |

### TC-DASH-008 — Empty workspace (P0)

| Step | Action                          |
| ---- | ------------------------------- |
| 1    | New workspace with zero sources |

**Expected:** Empty state with CTA to import; no crash.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

---

## 8. History (`/history`)

### TC-HIST-001 — Timeline visible (Starter+, P0)

| Step | Action                                                    |
| ---- | --------------------------------------------------------- |
| 1    | As **Starter** or **Pro**, open `/history` after analyses |
| 2    | Compare periods if offered                                |

**Expected:** Events/snapshots listed; Free sees upgrade or empty per product rules.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-HIST-002 — History depth cap (P1)

| Step | Action                                          |
| ---- | ----------------------------------------------- |
| 1    | Starter: verify ~3 periods; Pro: deeper history |

**Expected:** Older periods truncated on Starter.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

---

## 9. Chat

### TC-CHAT-001 — Per-dataset chat (P0)

| Step | Action                                                      |
| ---- | ----------------------------------------------------------- |
| 1    | Open `/chat` or dataset chat panel                          |
| 2    | Select a source                                             |
| 3    | Ask: `What channel had the highest returns?` (Slick Styles) |
| 4    | Ask follow-up                                               |

**Expected:** Answers grounded in data; errors handled; history scrolls.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-CHAT-002 — Workspace chat (P1)

| Step | Action                                |
| ---- | ------------------------------------- |
| 1    | Use workspace-level chat if available |
| 2    | Ask cross-source question             |

**Expected:** Uses multiple datasets contextually.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-CHAT-003 — Chat plan limits (P1)

| Step | Action                                  |
| ---- | --------------------------------------- |
| 1    | Free: send until chat cap (~3 messages) |
| 2    | Paid: confirm higher limit              |

**Expected:** Clear limit message; no silent failure.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

---

## 10. Plans & billing (Razorpay test mode)

### TC-BILL-001 — Pricing while logged in (P0)

| Step | Action                     |
| ---- | -------------------------- |
| 1    | Sign in → `/pricing`       |
| 2    | Start **Starter** checkout |

**Expected:** Razorpay modal or redirect opens; test keys load.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-BILL-002 — Successful subscription (P0)

| Step | Action                                            |
| ---- | ------------------------------------------------- |
| 1    | Complete Razorpay **test** payment / mandate auth |
| 2    | Wait for redirect (no manual “back to merchant”)  |

**Expected:** Auto-redirect to `/pricing/success` then `/dashboard?subscription=started`; verify-checkout succeeds; `/account` shows Starter or Pro; limits increase. User should **not** remain on `api.razorpay.com` subscription page unless `NEXT_PUBLIC_RAZORPAY_HOSTED_CHECKOUT=true`.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-BILL-003 — Failed / cancelled payment (P1)

| Step | Action                   |
| ---- | ------------------------ |
| 1    | Cancel Razorpay checkout |

**Expected:** User stays on Free (or prior plan); friendly message; can retry.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-BILL-004 — Webhook updates plan (P1)

| Step | Action                                                                                         |
| ---- | ---------------------------------------------------------------------------------------------- |
| 1    | After successful payment, confirm plan in DB/UI without manual refresh (or after refresh only) |

**Expected:** Webhook configured at `https://<api>/api/billing/razorpay/webhook`; plan syncs.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-BILL-005 — Upgrade Starter → Pro (P2)

| Step | Action                                   |
| ---- | ---------------------------------------- |
| 1    | From Starter, upgrade to Pro via pricing |

**Expected:** New plan reflected; workspace cap increases.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

---

## 11. Account & account deletion

### TC-ACC-001 — Account page (P0)

| Step | Action                           |
| ---- | -------------------------------- |
| 1    | Open `/account`                  |
| 2    | Verify email, plan, usage meters |

**Expected:** Matches effective plan; usage numbers plausible.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-ACC-002 — Delete account (P0)

| Step | Action                                         |
| ---- | ---------------------------------------------- |
| 1    | Use **Delete account** on disposable test user |
| 2    | Confirm                                        |

**Expected:** Signed out; cannot access old data; re-register with same email works as new user.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

---

## 12. UI, accessibility & cross-browser

### TC-UI-001 — Dark mode (P1)

| Step | Action                                          |
| ---- | ----------------------------------------------- |
| 1    | Toggle dark/light on dashboard, upload, pricing |

**Expected:** Readable contrast; charts visible; logo visible.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-UI-002 — Mobile width (P1)

| Step | Action                              |
| ---- | ----------------------------------- |
| 1    | Resize to ~390px width or use phone |
| 2    | Navigate upload → dashboard         |

**Expected:** Usable layout; nav accessible; no horizontal overflow.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

### TC-UI-003 — Browsers (P1)

| Step | Action                                                       |
| ---- | ------------------------------------------------------------ |
| 1    | Repeat TC-DASH-001 + TC-UP-002 on Chrome, Safari, or Firefox |

**Expected:** Core flows work on primary + one alternate browser.

| Pass? | Notes |
| ----- | ----- |
| ☐     |       |

---

## 13. Production / ops smoke (after deploy)

| ID         | Check                                                                             | Pass? |
| ---------- | --------------------------------------------------------------------------------- | ----- |
| TC-OPS-001 | Redeploy backend → Neon data still there (users, datasets list)                   | ☐     |
| TC-OPS-002 | Redeploy backend → **uploaded files** still open charts (only if persistent disk) | ☐     |
| TC-OPS-003 | Cold start: first API request after idle < acceptable time                        | ☐     |
| TC-OPS-004 | OTP email delivers from production domain                                         | ☐     |
| TC-OPS-005 | Favicon shows Snaptix icon in browser tab                                         | ☐     |

---

## 14. Release sign-off

| Area              | P0 pass? | Open P0 bugs |
| ----------------- | -------- | ------------ |
| Auth & onboarding | ☐        |              |
| Import / sources  | ☐        |              |
| Dashboard & AI    | ☐        |              |
| Chat              | ☐        |              |
| Billing           | ☐        |              |
| Account / legal   | ☐        |              |
| Ops / persistence | ☐        |              |

**Release decision**

| Decision                          | Name / date |
| --------------------------------- | ----------- |
| ☐ **Go** — all P0 passed          |             |
| ☐ **No-go** — list blockers below |             |

**Blockers:**

1.
2.
3.

---

_Generated for Snaptix codebase structure as of release prep. Plan limits reference `backend/services/subscription_usage.py`._

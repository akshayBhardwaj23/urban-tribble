# Integrations: activation plan

**Status:** proposal, pre-implementation.
**Context:** `/integrations` is live in the nav but renders a read-only "Coming soon" catalog.
The backend behind it is largely built and deliberately switched off.

---

## 1. Ground truth — what already exists

This is not a greenfield feature. It is a mostly-complete feature behind two kill switches.

### Switched off by

| Switch | File | Value |
|---|---|---|
| `INTEGRATIONS_ENABLED` | `backend/config.py:94` | `False` → create/patch/refresh/test/oauth return **503** |
| `INTEGRATION_SCHEDULER_ENABLED` | `backend/config.py:98` | `False` → no background refresh loop |
| `INTEGRATIONS_COMING_SOON` | `frontend/src/lib/integrations-flags.ts` | `true` → catalog renders disabled cards |

### Already built (backend)

- **Data model** — `DataSourceIntegration` (`backend/models/models.py`), in baseline migration `0001`.
  `Dataset.integration_id` FK with `ON DELETE SET NULL`, so removing an integration keeps the dataset.
- **Provider catalog** — 16 providers across 3 tiers (`services/integration_registry.py`), each with
  declarative connection modes + form field definitions the UI renders generically.
- **Fetchers** — 11 working paths in `services/integration_connectors.py`:
  Google Sheets (published CSV), Excel/OneDrive (share link **and** Graph OAuth), generic export URL
  (Drive, Power BI), Stripe, Shopify, Postgres, GA4, Meta Ads, HubSpot, Salesforce, BigQuery.
- **Microsoft 365 OAuth** — complete round trip: authorize → callback → workbook picker → connect →
  sync, with refresh-token renewal (`services/integration_microsoft.py`, `services/integration_oauth.py`).
  **This is the only provider with a finished OAuth flow.**
- **Sync engine** — `services/integration_sync.py` reuses the *same* `ingest_dataframe` path as uploads,
  so a synced source produces a normal `Upload` + `Dataset` and inherits cleaning, column-role detection,
  dashboard planning, parquet caching, and timeline snapshots.
- **Dashboard stability** — `dashboard_plan_locked` means a refresh does **not** reshuffle KPIs/charts
  unless the schema actually changes (`services/dashboard_stability.py`). This is the right behaviour and
  is the single most important thing that makes "live data" not feel broken.
- **Post-sync AI briefing** — `services/integration_analysis.py`, plan-gated.
- **Scheduler** — in-process loop + an external cron endpoint `POST /api/integrations/run-scheduled`
  guarded by `INTEGRATION_CRON_SECRET`.
- **SSRF hardening on export URLs** — `_host_is_blocked` + per-redirect re-validation. Good work; note
  below that it does **not** cover every connector.

### Already built (frontend)

- Full typed API client (`frontend/src/lib/api.ts:963-1120`) — every endpoint is already wired.
- Dataset list and dataset detail already render integration state
  (`Live · <provider>`, "syncs every Nh", a Refresh button gated on the flag).
- The complete connect UI (catalog → mode picker → dynamic field form → OAuth workbook picker →
  connected list with refresh/schedule/remove) exists in git at `6390b2d^` and was replaced, not deleted.
  **Recovering it is a `git show`, not a rewrite.**

---

## 2. Gaps that must close before the switch flips

These are the reasons the feature is off, whether or not they were written down. Each is a real defect
against production traffic, not a nice-to-have.

### Blocking — security

1. **Credentials are stored in plaintext.** `config_json` holds Stripe secret keys, HubSpot tokens,
   Shopify admin tokens, Postgres connection strings, GA4/BigQuery service-account JSON, and Microsoft
   **refresh tokens** as cleartext in the DB. A DB dump or a read-only SQL leak is a full compromise of
   every connected customer system. Needs envelope encryption at rest + redaction on every read path.
2. **SSRF in the DB/CRM connectors.** `fetch_postgres` calls `create_engine(user_string)` and
   `fetch_salesforce` GETs a user-supplied `instance_url` — neither goes through `_host_is_blocked`.
   The export-URL path is hardened; these two are not. They can reach internal networks and cloud
   metadata endpoints.
3. **OAuth session store is process-local.** `_oauth_sessions` is a module dict
   (`services/integration_oauth.py:14`). With more than one uvicorn worker or container the Microsoft
   callback lands on a worker that has never heard of the session → "session not found or expired"
   on a random fraction of connects.

### Blocking — correctness and cost

4. **Integrations bypass plan quotas.** `assert_upload_allowed` is enforced on
   `routes/uploads.py:35` and `routes/datasets.py:469` but nowhere in the integration path. A Free user
   can connect a source and generate unlimited `Upload` rows on a 1-hour cadence. Analyses *are* gated
   (`integration_analysis.py:43`) but the failure is swallowed silently, so the user sees a sync with no
   briefing and no explanation.
5. **No row/column caps on sync.** `validate_frame_size` runs on both upload paths but never inside
   `ingest_dataframe`, so a synced source is not subject to `MAX_ROWS_PER_FILE` / `MAX_COLUMNS_PER_FILE`.
   An 8M-row BigQuery result goes straight into pandas, Prophet, and the parquet cache.
6. **Sync runs inline in the HTTP request, on the event loop.** `POST /api/integrations` awaits
   `sync_integration` → `ingest_dataframe` (LLM column-role call + dashboard planner) → optional
   `run_post_sync_analysis` (a second LLM call). These are blocking calls inside an `async def`.
   This is precisely the problem `upload_worker.py` was written to fix — its own docstring says so.
   Integrations reintroduce it.
7. **`syncing` is a terminal state on crash.** `find_due_integrations` filters status
   `in (active, pending, error)`, so an integration stuck in `syncing` is never picked up again — and the
   UI disables "Refresh now" while status is `syncing`. A process restart mid-sync bricks that connection
   with no user-recoverable path.
8. **The scheduler runs in every process.** The lifespan loop starts per worker with no leader election
   or row locking, so N workers means N concurrent syncs of the same integration, N sets of LLM calls,
   and interleaved writes to one dataset.
9. **No cap on integrations per workspace**, so nothing bounds scheduled fetch volume.
10. **Zero test coverage.** `backend/tests/` has three files, none touching integrations.

### Non-blocking but should be decided

11. **HTML error pages slip past the payload sniffer when whitespace-prefixed.**
    `_dataframe_from_bytes` does `content[:6].lstrip()` — it slices *before* it strips, so a
    leading newline shifts the window and the `<html` probe never fires. A server that emits
    whitespace before its login page gets parsed by pandas into an empty one-column dataset
    instead of raising the actionable "that's a web page, not a file" error. Found while writing
    the Phase 0 tests; one-line fix, scheduled into Phase 2.
12. **Google Sheets' only working mode requires "Publish to web"** — i.e. the customer makes their
    revenue sheet world-readable. For a business analytics product this is a footgun, not a feature.
    It should not be the flagship Sheets path.
13. **Removing an integration does not revoke upstream tokens.** Low severity, but it is what a privacy
    policy implies we do.

---

## 3. Which integrations to launch, and in what order

The product's job is a founder/ops read on revenue, cost, and profit. Order providers by *how directly
they feed that*, weighted by how much is already built and how little new surface each one adds.

### Wave 1 — "your spreadsheet, but it stays current" (launch)

| Provider | Why first | State |
|---|---|---|
| **Excel / OneDrive** | Only provider with a finished OAuth round trip. Same data shape as an upload — zero new semantics for dashboards or chat. | Code complete; needs the §2 hardening + an Azure app registration. |
| **Google Sheets (Google OAuth)** | The single most-requested source for a spreadsheet-analytics product, and it retires the "publish to web" footgun. Google OAuth already exists for sign-in (`GOOGLE_CLIENT_ID/SECRET` in `frontend/.env.local`), so this is an incremental scope + a Drive file picker, reusing the Microsoft flow's exact structure. | Fetcher exists for the CSV path; **OAuth flow is the one genuinely new build.** |

These two are the right launch pair because a synced workbook is *identical in shape* to an uploaded one.
Everything downstream — cleaning, column roles, dashboard plan, chat, timeline, alerts — already handles it.
Risk to the existing product is close to zero.

### Wave 2 — "the number that pays for the subscription"

| Provider | Why | State |
|---|---|---|
| **Stripe** | One secret key, no OAuth. Charges over time is exactly what the dashboard, forecast, and "what changed" were built to read. This is where *live* beats *upload*. | Fetcher complete. |
| **Shopify** | Large SMB segment; orders map cleanly onto the same revenue shape. | Fetcher complete. |

### Wave 3 — funnel and spend

HubSpot (private-app token), GA4 (service account), Meta Ads (system-user token). All three have working
fetchers. They need real credential UX (these are the flows where users get lost) plus per-provider docs.

### Park — keep visible as roadmap, keep disabled

Salesforce, Postgres, BigQuery, Snowflake, QuickBooks, Slack, Teams, Power BI.
Salesforce and Postgres have live code paths **and** the SSRF hole from §2.2 — the fix is either to
harden them or to set `available: false` in the registry. Given they are enterprise-tier and not the
launch audience, **set them unavailable now** and revisit with the hardening.

---

## 4. How a connection threads through the existing workflow

The good architectural decision is already made: **a synced source becomes a normal dataset.** Keep it.

```
Connect (OAuth or credentials)
        │
        ▼
sync_integration ──► fetch_provider_data ──► DataFrame
        │
        ▼
ingest_dataframe          ← the SAME function uploads use
   ├─ DataCleaner
   ├─ ColumnDetector + LLM column roles
   ├─ DashboardPlanner   ← skipped when plan is locked and schema is unchanged
   ├─ cleaned parquet
   └─ Upload + Dataset rows
        │
        ├──► workspace timeline snapshot  (history / "what changed")
        ├──► post-sync AI briefing        (plan-gated)
        │
        ▼
Everything downstream is unchanged:
  /dashboard overview · /datasets/[id] · /chat · alerts · weekly & monthly summaries · forecasting
```

The only place a synced dataset should look different to a user is a **freshness marker** — a "Live ·
Stripe · synced 2h ago" badge — which `/datasets` and `/datasets/[id]` already render.

### UI surfaces that change

| Surface | Change |
|---|---|
| `/integrations` | Restore the full connect UI from `6390b2d^`, gated per-wave rather than all-or-nothing. |
| `/datasets` | Drop "integrations are coming soon" copy; the `Live · provider` badge already works. |
| `/datasets/[id]` | Un-gate the existing "Refresh data" button; add last-sync / next-sync and a visible error state. |
| `/dashboard` | No change. Optional later: a stale-source nudge in recommended actions. |
| `/pricing`, marketing | **Do not touch until Wave 1 ships.** Product brief §F currently says "do not market live sync"; that stays true until it isn't. |

---

## 5. Proposed implementation order

Each phase ends green, with both flags still defaulting to off. Nothing user-visible changes until Phase 5.

**Phase 0 — safety net (no behaviour change) — DONE**
`backend/tests/test_integrations.py`, 51 tests, no source changes. Covers registry integrity,
catalog↔dispatch drift, the SSRF blocklist, OneDrive URL/token handling, payload sniffing, signed
OAuth state (forgery, tampering, expiry), the OAuth session store, refresh-interval clamping,
credential redaction in API responses, and the `find_due_integrations` state machine.
Two known gaps (§2.7 stuck `syncing`, §2.11 HTML sniffer) are asserted as they behave *today* and
labelled in-test, so fixing them shows up as a deliberate test edit rather than a silent change.
Full suite: 80 passed, `ruff check` clean.

**Phase 1 — secure the credential store — DONE**
`services/integration_credentials.py` seals `config_json` as `enc:v1:<fernet token>` using
`MultiFernet` over a comma-separated `INTEGRATION_CREDENTIALS_KEY` (first key encrypts, all keys
decrypt, so rotation is two deploys rather than an outage). Encrypt on all four write sites
(create, OAuth complete, patch, and the post-fetch re-persist that captures rotated Microsoft
tokens); decrypt on both read sites. `IntegrationCredentialsError` subclasses
`IntegrationNotConfiguredError`, so an unreadable row travels the existing error plumbing — a 422
with an actionable message that parks the integration in `error` — instead of a 500.

Rows without the prefix are read as legacy cleartext, so nothing written before this change breaks;
`scripts/encrypt_integration_credentials.py` upgrades them in bulk and doubles as the rotation tool.
With no key configured the column stays cleartext, which is exactly the prior behaviour, so local
development needs no setup — and `collect_runtime_setting_errors` refuses to boot a production
deployment in that state, or with a malformed key.

Verified end to end against a SQLite database: cleartext row → backfilled → secret absent from the
file → readback correct → second run idempotent → wrong key exits 1 with no data loss → `new,old`
rotation re-seals → readable under the new key alone.
Adds one dependency, `cryptography==46.0.3`. Suite: 99 passed, `ruff check` clean.

*Deliberately not done here:* binding ciphertext to its row id (AAD), which would defend against an
attacker who already has database **write** access. Fernet has no AAD parameter and the id is not
known before flush, so this needs an explicit id assignment; the threat is strictly weaker than the
one being fixed. Noted for later.

**Phase 2 — make sync safe to run**
`validate_frame_size` inside `ingest_dataframe`; `assert_upload_allowed` on the integration path with a
surfaced, non-swallowed plan error; move sync onto the existing worker pool so the endpoint returns
immediately and the UI polls (mirroring the upload flow the app already has); a `syncing` heartbeat +
stale-lock reclaim so a crash can't brick a connection; per-workspace integration cap; DB-level claim on
`find_due_integrations` so only one worker takes a row.

**Phase 3 — fix the OAuth session store**
Move `_oauth_sessions` to the database (short-TTL table) so the callback is worker-independent.
Set `available: false` on Salesforce, Postgres, Snowflake, BigQuery in the registry.

**Phase 4 — build Google Sheets OAuth**
The one net-new connector, deliberately built *after* the platform is safe, modelled on the Microsoft
flow that already works end to end.

**Phase 5 — restore the UI and flip the switch**
Recover the connect UI from git; replace the single `INTEGRATIONS_COMING_SOON` boolean with a
per-provider availability read from the catalog the backend already sends, so waves ship independently;
enable Wave 1 in production with the cron endpoint (not the in-process loop) driving refreshes.

**Phase 6 — Wave 2 (Stripe, Shopify), then Wave 3.**

---

## 6. Not breaking what works

- **Both flags stay `False` by default** through Phases 0–4. Every change lands on `main` dark.
- **Per-provider gating replaces the global flag** so one bad connector never takes down the page.
- **`ingest_dataframe` is shared with uploads** — the two changes proposed to it (size validation, plan
  check) tighten limits that uploads *already* enforce elsewhere, so upload behaviour is unchanged. This
  is the one file where a regression would reach existing users; it needs test coverage before it is
  touched, which is why Phase 0 is first.
- **The cron endpoint, not the in-process loop**, drives production refreshes — one caller, no
  duplicate-worker problem, and an instant kill switch by unsetting the secret.
- **Marketing copy moves last**, after a wave is live and verified.

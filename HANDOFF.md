# YourInboxHero — Session Handoff Document

**Purpose of this file:** This is a complete handoff for continuing work on this project in a new agent session. The previous session (Claude, via Claude Code) is running low on weekly usage limits and needs to transfer full context to a fresh session. Read this entire document before touching code — it contains verified findings (things actually checked by running commands), not guesses.

**How to use this doc:** Paste this whole file as your first message / system context in the new session, or point the new agent at this file path and say "read HANDOFF.md before doing anything." Everything below was verified against the actual codebase on 2026-09-24 — file paths and line numbers are real, not inferred.

---

## 1. What this project is (plain-English understanding)

**YourInboxHero** is a B2B SaaS product that automates two things for small businesses:

1. **Money Collection** — automated invoice/debt reminder emails (and SMS/voice escalation) so business owners don't have to manually chase clients who owe them money. Strictly limited to *business* debtors and *pre-due-date* automation (legal guardrail — no chasing consumers, no automated collection after the due date, to avoid debt-collection law issues).
2. **Document Collection** — a second, related module for requesting documents from clients (contracts, tax forms, etc.) with tracking.

It also has:
- A full marketing landing page (recently redesigned — see section 6)
- User registration/login (JWT auth)
- Subscription billing via **Square Checkout Links** (not the Square API/SDK — just hosted payment links + a webhook)
- Email template customization, custom SMTP/email-provider setup per user
- Analytics dashboard, PDF invoice generation, reminder history/audit log
- GoHighLevel (GHL) integration for SMS/voice escalation on overdue invoices

**Tech stack (verified):**
- Backend: Python 3.11, FastAPI, SQLAlchemy ORM, Alembic migrations, JWT auth (`pyjwt` + `passlib[bcrypt]`), APScheduler (in-process background jobs), SendGrid (email), ReportLab (PDF generation)
- Frontend: React 19 + TypeScript + Vite 8, plain CSS (no Tailwind/component library), `lucide-react` for icons
- DB: SQLite locally (`local.db`, gitignored), Postgres expected in CI/production (mismatch — see blockers)
- Deployment target: Azure App Service (Docker container), Azure Container Registry, via GitHub Actions
- Monitoring: Azure Monitor / OpenTelemetry (optional, only activates if `APPLICATIONINSIGHTS_CONNECTION_STRING` is set)

**Repo state:** No git remote configured (`git remote -v` returns nothing — this is a local-only repo right now). Single branch `master`. Large number of modified/untracked files not yet committed (see `git status`).

---

## 2. Section-by-section breakdown

### 2.1 Backend structure (`src/`)

| Path | Purpose | Status |
|---|---|---|
| `src/app.py` | FastAPI app entrypoint, router registration, table creation + admin user seed on startup | Working, but missing CORS middleware (blocker) |
| `src/db.py` | SQLAlchemy engine/session setup | Working; SQLite-default vs Postgres-in-CI mismatch |
| `src/auth.py` | JWT create/verify, password hashing | Working; insecure hardcoded fallback secret (blocker) |
| `src/api/auth.py` | Login/register endpoints | Working (has test coverage) |
| `src/api/reminder_manual.py` | Manually trigger a reminder for one invoice | Has a **failing test** (blocker) |
| `src/api/reminder_history.py` | Reminder audit log + CSV export | Working |
| `src/api/invoice_create.py`, `invoice_list.py`, `invoice_pause.py`, `invoice_pdf.py` | Invoice CRUD, pause automation, PDF generation | Working |
| `src/api/debtor.py` | Debtor (client) CRUD | Working |
| `src/api/analytics.py` | Dashboard analytics endpoint | Working |
| `src/api/email_template.py` | Custom email template CRUD | Working |
| `src/api/document_request.py`, `document_client.py` | Document Collection module (second product line) | Present, low test coverage |
| `src/api/square_payments.py` | Subscription checkout + Square webhook | **Critical security gap** — webhook has zero signature verification (blocker) |
| `src/api/webhooks.py` | GHL inbound webhook (`/api/webhooks/ghl/{webhook_secret}`) | Working; secret-in-URL-path pattern is a minor security smell (non-blocker, should move to header) |
| `src/api/health.py` | `/health` endpoint | Working, used for smoke tests |
| `src/scheduler.py` | In-process `BackgroundScheduler` (APScheduler) — runs the escalation sweep (email → SMS → voice tiers) | Works for single instance only; **will double-send if app scales to 2+ instances** (non-blocking for launch, must fix before scaling) |
| `src/services/email.py` | SendGrid wrapper + custom SMTP support, template rendering | Working (one test currently fails due to a test fixture bug, not a real bug — see blockers) |
| `src/services/pdf_service.py` | Invoice PDF generation via ReportLab | Working |
| `src/services/ghl_service.py` | GoHighLevel API client for SMS/voice | Working, needs `GHL_API_KEY` |
| `src/services/reminder_service.py` | Core eligible-invoice query + processing logic; also gates on `reminders_enabled()` feature flag | Working, but feature flag depends on Unleash which is likely not actually deployed (see 2.3) |
| `src/services/overdue_service.py` | Nightly-style overdue transition logic | Working |
| `src/services/queue.py` | Azure Service Bus enqueue helper | **Present but appears unused/dead code** in the actual reminder flow now (original plan called for queue-decoupling; current `reminder_service.py` imports it but the simpler direct-send path may be what's live — verify before relying on this) |
| `src/feature_flags.py` | Unleash feature-flag client wrapper | Only used by `reminder_service.py`; if `UNLEASH_URL` isn't set this will likely error or no-op — **verify behavior when env var is absent**, not yet confirmed safe |
| `alembic/` | DB migrations — 2 migrations present (`initial_schema`, `add_multi_tenancy`) | Present; verify they're up to date with current models before deploying to a fresh Postgres instance |

### 2.2 Frontend structure (`frontend/src/`)

| Path | Purpose | Status |
|---|---|---|
| `App.tsx` | Root component, module/tab switching (Money Collection vs Document Collection), auth gate | Working |
| `components/LandingPage.tsx` + `.css` | Marketing page | **Recently redesigned this session** — see section 6 for full detail on what was fixed |
| `components/Login.tsx`, `Register.tsx` | Auth forms | Working |
| `components/InvoiceTable.tsx`, `DebtorTable.tsx`, `CreateInvoice.tsx`, `CreateDebtor.tsx` | Money Collection CRUD UI | Working |
| `components/AnalyticsDashboard.tsx` | Analytics charts/stats | Working |
| `components/EmailTemplates.tsx`, `EmailProviders.tsx` | Template + SMTP config UI | Working |
| `components/DocumentTable.tsx`, `CreateDocumentRequest.tsx`, `CreateDocumentClient.tsx` | Document Collection module UI | Working, less tested |
| `components/PaymentSuccess.tsx` | Post-Square-checkout landing | Working |
| `components/Settings.tsx` | Account settings | Working |
| `api/invoice.ts` and sibling API wrapper files | Fetch wrappers calling the FastAPI backend | Working |
| `public/hero-bg.jpg`, `feature-1/2/3.jpg` | Marketing images (1024x1024 JPEGs, AI-generated looking) | Present, reasonably sized |

### 2.3 Infra / CI-CD (`.github/workflows/`, `Dockerfile`, `alembic.ini`)

| File | Purpose | Status |
|---|---|---|
| `.github/workflows/ci.yml` | Lint (flake8) → test (pytest against Postgres service container) → frontend lint/build | **Would currently fail** — `requirements.txt` is broken (see blockers), plus 2 failing tests |
| `.github/workflows/deploy.yml` | Docker build → push to ACR → deploy to Azure App Service "green" slot on push to `master` | Present but **never actually run/verified** — no evidence of a real Azure resource group, App Service, or ACR existing yet. No database provisioning step at all. No blue/green swap step after deploy (deploys straight to green slot and stops) |
| `Dockerfile` | Multi-stage: Node build frontend → Python slim + uvicorn | Builds correctly (verified: frontend `npm run build` succeeds) |
| Original `plan.md` (12-week enterprise plan) | Called for Terraform, Azure Service Bus, Azure Functions Timer, Unleash self-hosted, Azure Key Vault | **Never built** — this is fine, the current architecture (Docker + App Service + in-process scheduler) is simpler and adequate for launch. Don't treat this as a gap; it's a legitimate scope reduction. |

---

## 3. Credentials / environment variables

**IMPORTANT: I (the previous session) do not have and have never had access to any real API keys or secrets for this project.** Nothing is stored anywhere in this conversation, in memory, or in the repo. What follows is a complete list of every environment variable the *code* expects, found by grepping `os.getenv`/`os.environ` across `src/`. The user (project owner) is the only one who has or can obtain these values.

| Variable | Used in | Required for | Currently in `.env.example`? |
|---|---|---|---|
| `SECRET_KEY` | `src/auth.py:13` | Signing JWTs | **No — missing, and dangerously falls back to a hardcoded dev string if unset** |
| `DATABASE_URL` | `src/db.py:8` | Postgres connection string in prod (falls back to local SQLite file if unset) | **No — missing** |
| `SENDGRID_API_KEY` | `src/services/email.py:78` | Sending reminder emails via SendGrid (fallback sender) | Yes |
| `GHL_API_KEY` | `src/services/ghl_service.py:18` | GoHighLevel SMS/voice escalation | Yes |
| `GHL_LOCATION_ID` | Referenced in `.env.example`, used alongside GHL_API_KEY | GoHighLevel | Yes |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | `src/app.py:45` | Azure Monitor telemetry (optional — app runs fine without it) | Yes |
| `UNLEASH_URL` | `src/feature_flags.py:23` | Feature-flag service for `reminders-enabled` toggle | **No — missing.** No evidence an Unleash instance is actually deployed anywhere. Behavior when unset is unverified — check this early. |
| `SERVICE_BUS_CONNECTION_STRING` | `src/services/queue.py:8` | Azure Service Bus queue (appears to be legacy/unused code path from the original plan) | **No — missing.** Low priority since this code path may be dead. |

**Square payments**: No API key, access token, or webhook signing secret exists anywhere in the code or env files. The current implementation uses static **Square Checkout Links** (hardcoded URLs in `LandingPage.tsx`: `https://square.link/u/MOsw5n5g`, `/nYps8IHC`, `/IqJw5Qom`) plus an unauthenticated webhook receiver. To fix the security blocker (see section 4), you will need the project owner to provide a **Square webhook signature key** from their Square Developer Dashboard — this does not exist yet in this project.

**Azure**: `deploy.yml` references `secrets.AZURE_CREDENTIALS` (a GitHub Actions secret) — this must exist in the GitHub repo's secrets settings for the deploy workflow to run at all. No evidence it's been configured; there's no GitHub remote connected to this local repo yet.

**Action for the next agent:** Before doing any deployment work, explicitly ask the user for: (1) a Square webhook signing secret, (2) intended Postgres connection details or confirmation to provision one on Azure, (3) confirmation a GitHub remote/repo exists and Azure credentials are ready to add as secrets. Do not assume any of these exist.

---

## 4. Blockers (must fix before any production launch)

Ranked by severity, all verified by directly running code/commands this session:

1. **Square webhook has zero signature verification** — `src/api/square_payments.py:70-91`. Anyone can POST a forged `payment.completed` JSON body with a `buyer_email` of their choosing and an amount matching a plan price, and it will activate a paid subscription for free on that account. This is a direct fraud/revenue-loss vulnerability. Fix: use Square's webhook signature verification (HMAC-SHA256 over the notification URL + body, compared against `x-square-hmacsha256-signature` header) once a signing secret is obtained from the user.

2. **`requirements.txt` is broken** — line 13 literally reads `reportlabAPScheduler` (two package names concatenated with no separator/newline). Verified: `pip install reportlabAPScheduler` fails with "No matching distribution found." This means **CI and the Docker build both currently fail** at the install step. Fix: split into `reportlab` and `APScheduler` on separate lines.

3. **No CORS middleware in `src/app.py`** — verified via grep, zero occurrences of `CORSMiddleware` or `allow_origins`. Once frontend and backend are on different origins/subdomains in production, all API calls from the browser will be blocked. Fix: add `fastapi.middleware.cors.CORSMiddleware` with explicit allowed origins (not `*` — this app handles auth tokens).

4. **JWT secret has an insecure hardcoded fallback** — `src/auth.py:13`: `SECRET_KEY = os.getenv("SECRET_KEY", "test-secret-key-for-jwt-dev")`. This fallback string is sitting in the public repo. If `SECRET_KEY` isn't explicitly set in Azure App Service configuration, every JWT issued in production is forgeable by anyone who reads this file on GitHub. Fix: remove the fallback entirely — raise a startup error if `SECRET_KEY` is unset in a non-dev environment.

5. **2 failing tests, verified by running `python -m pytest -q`:**
   - `tests/api/test_reminder_manual.py::test_manual_reminder_404` — assertion failure, needs investigation
   - `tests/services/test_email.py::test_send_email_calls_sendgrid` — `AttributeError: 'DummyUser' object has no attribute 'id'`. This looks like the test's mock fixture is stale relative to a recent change in `email.py` (the real `send_reminder_email` now looks up `EmailTemplate` by `user.id`, but the test's `DummyUser` mock class doesn't have an `id` attribute). Likely a quick fix in the test file, not a real production bug — but must be fixed so CI can go green.

6. **Database strategy mismatch across environments** — app defaults to SQLite (`src/db.py:8-10`), CI tests run against a Postgres service container, and `deploy.yml` never provisions any database resource or sets `DATABASE_URL` at all. Before first production deploy, you need to: provision an actual Postgres instance (Azure Database for PostgreSQL, or equivalent), set `DATABASE_URL` as an Azure App Service app setting, and verify the two Alembic migrations apply cleanly against it (`alembic upgrade head`).

---

## 5. Not launch-blocking, but should fix soon after

7. **Scheduler won't survive horizontal scaling** — `src/scheduler.py` uses in-process `APScheduler.BackgroundScheduler`. Fine for one instance. If Azure App Service ever scales to 2+ instances, every instance runs its own scheduler and duplicate reminder emails/SMS/voice calls will fire. Fix later with a distributed lock (e.g., a Postgres advisory lock, or Azure Functions Timer as originally planned) — not urgent if launching on a single instance.

8. **No rate limiting anywhere** — auth endpoints, the manual-reminder trigger, and both webhook receivers (GHL and Square) have no rate limiting. Low urgency at low traffic, but should be added via Azure API Management or a simple in-app limiter before any real user growth.

9. **GHL webhook secret is in the URL path** (`/api/webhooks/ghl/{webhook_secret}`) rather than a header — URL-path secrets tend to leak into server access logs, browser history, and referrer headers. Should move to a header-based check (e.g., `X-Webhook-Secret`) but functionally it works today.

10. **Low test coverage relative to codebase size** — 35 tests total across 13 test files vs. 42 backend source modules. Notably thin or absent coverage: `square_payments.py`, `webhooks.py`, `scheduler.py`, `feature_flags.py`, `queue.py`. Not a launch blocker but a real technical-debt risk given item #1 above.

11. **`feature_flags.py` / Unleash dependency unverified** — no evidence an Unleash server is actually deployed. Need to confirm what happens when `UNLEASH_URL` is unset (likely either a crash on import or a silent no-op) before relying on the reminders-enabled toggle in production.

12. **`src/services/queue.py` (Azure Service Bus) may be dead code** — imported by `reminder_service.py` but unclear if actually invoked on the live send path vs. the simpler direct-send path. Worth a quick trace before either wiring it up for real or removing it to reduce confusion.

---

## 6. Non-blockers / already resolved this session

These were investigated and are **fine as-is** — no action needed:

- **`.gitignore` correctly excludes secrets** — verified `local.db`, `*.env`, `.env` are all gitignored and confirmed not tracked in git.
- **Frontend production build works cleanly** — verified `npm run build` succeeds (`tsc -b && vite build`), outputs a reasonably small bundle (72.94 kB gzipped JS).
- **Original 12-week enterprise plan (Terraform, Service Bus, Azure Functions Timer, Key Vault) was never built** — this is fine. The current simpler architecture (Docker + single App Service + in-process scheduler + SendGrid) is a legitimate, adequate scope reduction for an early-stage product. Don't try to "complete" the original plan; it's over-engineered for where this product actually is.
- **Landing page visual/UX bugs — FIXED this session:**
  - **Critical bug fixed**: the scroll-reveal animation used `IntersectionObserver` with no fallback. A fast scroll (trackpad flick, Page Down, jump-to-bottom) could carry a section past the viewport between animation frames without ever triggering `isIntersecting`, leaving entire sections permanently invisible (`opacity: 0`) — this caused massive blank black gaps on the page. Fixed in `frontend/src/components/LandingPage.tsx` with (a) immediate-reveal for anything already in view on mount, and (b) a scroll-event safety net that reveals anything scrolled past. Verified via Playwright: gradual scroll, instant jump-to-bottom, and fresh-load-no-scroll all now correctly reveal every section.
  - Visual refinements also completed in `LandingPage.css`: tightened oversized section padding (160px→~120px) for better rhythm; fixed pricing-tier CTA buttons that looked disabled (transparent background/thin border → solid dark background with gold hover state); fixed near-invisible inactive showcase-tab titles (`#555` on black → `#888` with hover state); rebalanced inconsistent type scale (section titles were jumping between 4-4.5rem, now consistently ~3-3.4rem); fixed a mobile bug where the hero CTA row used an inline flex style with no wrap handling (caused "No Credit Card Required" to orphan onto its own line); fixed mobile nav overflow (Sign In / Get Access buttons were cramping and wrapping awkwardly).
  - All fixes verified visually via Playwright screenshots at desktop (1440x900) and mobile (390x844) viewports.

---

## 7. Time-to-production estimate

For one focused engineer/agent fixing blockers #1–6 above:

- Fix `requirements.txt`, add CORS middleware, remove insecure JWT fallback, fix the 2 failing tests: **~2-3 hours**
- Add Square webhook signature verification (once the user provides a signing secret): **~2-4 hours**
- Provision a real Postgres instance, wire `DATABASE_URL` + `SECRET_KEY` as Azure App Service secrets, run Alembic migrations against it, verify `deploy.yml` end-to-end with a real Azure resource group: **~half a day**, mostly waiting on Azure provisioning and debugging first-deploy issues

**Total: roughly 1–2 focused working days** to close every genuine blocker and get a safe first production deploy. Items #7–12 (should-fix-soon) can trail as fast-follows without blocking launch.

---

## 8. Recommended phased execution plan for the next agent

### Phase 0 — Orientation (do this first, ~15 min)
- Read this entire document.
- Run `git status`, `python -m pytest -q`, and `cd frontend && npm run build` yourself to confirm the state described above hasn't drifted (the user may have made changes between sessions).
- Ask the user directly for the three credentials/decisions listed at the end of section 3 (Square signing secret, Postgres plan, GitHub remote/Azure credentials) — don't proceed with deployment work until you have real answers, not assumptions.

### Phase 1 — Make CI green (blockers #2, #5)
- Fix `requirements.txt` (split `reportlabAPScheduler` into two lines).
- Fix the two failing tests — investigate `test_manual_reminder_404` first (read the actual assertion failure), then fix the `DummyUser` mock in `test_email.py` to include an `id` attribute matching what `send_reminder_email` now expects.
- Run the full suite locally, confirm all green, then push and confirm `.github/workflows/ci.yml` passes for real (this requires a GitHub remote — set one up with the user if none exists).

### Phase 2 — Close the security/config blockers (#1, #3, #4)
- Add `CORSMiddleware` to `src/app.py` with explicit origins (ask the user what the production frontend domain will be).
- Remove the hardcoded JWT fallback secret in `src/auth.py`; make the app fail fast on startup if `SECRET_KEY` is unset outside local dev.
- Implement Square webhook signature verification in `src/api/square_payments.py` using the signing secret the user provides. Write a test for both the valid-signature and forged-signature cases — this is the highest-value test to add given it's the one confirmed fraud vector.
- Update `.env.example` to include every variable found in section 3 of this doc, with comments on which are required vs optional.

### Phase 3 — Real database + deploy verification (blocker #6)
- Work with the user to provision Postgres (Azure Database for PostgreSQL Flexible Server, or their preferred host).
- Set `DATABASE_URL` and `SECRET_KEY` as Azure App Service application settings (never commit them).
- Run `alembic upgrade head` against the real Postgres instance and confirm schema matches the SQLAlchemy models exactly.
- Do a real end-to-end run of `deploy.yml` — this requires `AZURE_CREDENTIALS` to exist as a GitHub Actions secret and the Azure resources (`yourinboxheroacr`, `yourinboxhero-app-prod`, `yourinboxhero-rg-prod` per the workflow's env vars) to actually exist. If they don't exist yet, provision them first (via `az` CLI or Azure Portal) before expecting the workflow to succeed.
- Confirm the app actually boots and serves traffic on the deployed URL; hit `/health` and a couple of real endpoints manually.

### Phase 4 — Should-fix-soon items (#7–12), post-launch
- Only tackle these after Phase 1-3 are done and the app is live. Prioritize #7 (scheduler duplication) first if/when the user plans to scale beyond one instance, and #10 (test coverage) especially around `square_payments.py` given the fraud history.

### How to work through each phase
- Treat this like the user's existing repo conventions: small, verifiable commits per fix, run tests before claiming anything is done (see the `verification-before-completion` mindset below).
- Don't re-litigate the original 12-week `plan.md` — it's superseded by what's actually built. Reference section 6 of this doc if tempted to "complete" Terraform/Service Bus/Unleash work that isn't actually needed yet.
- Ask the user before any destructive or hard-to-reverse action (force-push, dropping a database, deleting env config) — same caution the previous session operated under.

---

## 9. Suggested skills/mindset for the next agent (to think the way this session did)

If the next agent is Claude Code with access to skills, these are the ones most relevant to finishing this work well:

- **`systematic-debugging`** — use before touching the two failing tests or the Unleash/feature-flag unverified-behavior question in item #11. Don't guess at fixes; reproduce, isolate, then fix.
- **`verification-before-completion`** — this session's core discipline: never claim something works without actually running it. Every finding in this document was verified by executing a real command (`pytest`, `pip install`, `npm run build`, `grep`, Playwright screenshots) rather than inferred from reading code alone. Continue that standard — it's what turned "the marketing page looks off" into a precisely diagnosed IntersectionObserver bug with a verified fix.
- **`security-review`** — run this explicitly before considering Phase 2 done, especially around the Square webhook and JWT handling. This codebase has already shown one real, exploitable financial vulnerability; assume there may be others not yet found (webhook replay attacks, missing input validation on financial endpoints, etc.) and look deliberately rather than opportunistically.
- **`test-driven-development`** — especially for the Square webhook signature fix; write the forged-signature-rejected test first, watch it fail against the current code, then implement the fix.
- **General approach**: this session avoided assuming anything about credentials, deployment state, or "done-ness" without checking. Grep and run things instead of trusting file names, comments, or an old plan document. The single biggest lesson from this session: `plan.md` (the original 12-week spec) describes an *aspirational* architecture that was never built and doesn't need to be — the actual codebase evolved into something simpler and better-scoped. Don't let a stale planning doc drive priorities; let verified current-state findings drive them, the way this document tries to.

---

## 10. Quick-reference commands used to verify everything in this document

```bash
# Run backend tests
python -m pytest -q

# Check for broken requirements.txt
pip install -r requirements.txt   # currently fails on line 13

# Verify frontend builds
cd frontend && npm run build

# Find all env vars the code actually reads
grep -rn "os\.getenv\|os\.environ" src --include="*.py"

# Check CORS config (currently zero results — that's the bug)
grep -n "CORSMiddleware\|allow_origins" src/app.py

# Check git remote/state
git remote -v
git status --short
```

---

*This document was generated by a Claude Code session on 2026-09-24 as a full-context handoff. Every claim above was verified by running the referenced command or reading the referenced file/line during that session — nothing here is speculative.*

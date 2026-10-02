# YourInboxHero — Production Readiness Plan

Source: full codebase audit (2026-10-01/02). Each item below is a concrete, file-level fix. Ordered by severity, then by dependency (items that unblock other items come first).

---

## CRITICAL (must fix before any paying customer)

### C1. No way to mark an invoice paid / stop chasing
**Problem:** No endpoint exists to set `InvoiceStatus.paid` or pause-then-resume. Once overdue, SMS/voice chase forever.
**Fix:**
- `src/api/invoice_pause.py` (or new `invoice_status.py`): add `POST /invoice/{id}/mark-paid` → sets `status=paid`, stops all future sweep matches (sweep queries already filter `status == overdue`, so this alone stops chasing).
- Add `POST /invoice/{id}/resume` to undo a pause (currently pause has no resume — check `invoice_pause.py` for existing pause-only logic and mirror it).
- Frontend: add "Mark Paid" button next to "Pause Reminders" in the invoice table (`frontend/src/components/...` wherever invoices render), wire to `markInvoicePaid()` in `frontend/src/api/invoice.ts`.
- Analytics (`src/services/...` / `src/api/analytics.py`) already sums `paid` status for "Total Recovered" — verify this connects once the status exists.
**Effort:** ~0.5 day (backend endpoint + test + frontend button).

### C2. Production safety mode is off
**Problem:** `ENVIRONMENT` is not set to `production` on Hetzner → `/docs` is public, `validate_production_settings()` never runs, and `SECRET_KEY` could silently fall back to the hardcoded dev value (`src/auth.py:21`).
**Fix:**
- SSH to Hetzner, add to `.env`: `ENVIRONMENT=production`
- Verify `SECRET_KEY` is set to a strong random value: `openssl rand -hex 32` if not already set, add to `.env`.
- Add both `ENVIRONMENT` and `SECRET_KEY` to `.env.example` with comments.
- Fix `src/auth.py:14-21` to read `SECRET_KEY` from `src.config.settings.get_settings()` instead of `os.getenv` directly, so it's covered by the same `validate_production_settings()` check as everything else (currently it's a separate, inconsistent code path).
- Restart container, confirm `curl https://api.yourinboxhero.com/docs` returns 404.
**Effort:** ~1 hour. **Do this one first — it's fast and highest risk-reduction per minute.**

### C3. Cross-tenant unique constraint collisions
**Problem:** `debtor.email` and `invoice.invoice_number` are globally unique (DB + app-level), not per-user. Second customer starting at "INV-001" or adding a debtor another customer already has gets blocked.
**Fix:**
- New Alembic migration:
  - Drop global unique constraint on `debtor.email`; add composite unique on `(user_id, email)`.
  - Drop global unique constraint on `invoice.invoice_number`; add composite unique on `(user_id, invoice_number)` — note `invoice` doesn't have `user_id` directly (it's via `debtor.user_id`), so either denormalize `user_id` onto `invoice`, or enforce this at the application layer only (check within the user's debtors) since a DB-level composite constraint across a join isn't directly expressible. Recommend: add `user_id` column to `invoice` (nullable initially, backfilled from `debtor.user_id`, then not-null) — this also simplifies every existing query that currently joins through `debtor` to scope by user.
- Update `src/api/debtor.py:43` and `src/api/invoice_create.py:39` to scope the uniqueness check by `current_user.id`.
- Update error messages to not leak whether the record exists for another tenant (generic "already exists" without confirming globally).
**Effort:** ~1 day (migration + backfill + query updates + tests).

### C4. Cancelled/past-due customers still get automated sends
**Problem:** `src/services/reminder_worker.py`, `src/scheduler.py` (`run_sms_reminders`, `run_voice_calls`), and `src/api/webhooks.py` (GHL) only check chase capacity, never `subscription_status`.
**Fix:**
- Add `user.subscription_status == "active"` check alongside the existing `has_chase_capacity(user)` check in:
  - `src/services/reminder_worker.py` (email path)
  - `src/scheduler.py:127` (`run_sms_reminders`)
  - `src/scheduler.py:216` (`run_voice_calls`)
  - `src/api/webhooks.py` (GHL-triggered invoice creation) — reject/skip invoice creation for inactive users.
- Consider factoring this into a single `can_send_chase(user)` helper in `src/services/usage_limits.py` that checks both capacity and status, used everywhere instead of duplicating the condition.
**Effort:** ~0.5 day.

### C5. Stripe billing lifecycle gaps
**Problem (5 sub-issues):**
- (a) `customer.subscription.updated` unhandled — plan changes in Stripe don't sync.
- (b) Repeat checkout by existing user overwrites `stripe_subscription_id`, double-bills.
- (c) No webhook event-ID deduplication — replays reset usage.
- (d) No reconciliation job for missed webhooks.
- (e) No Stripe customer portal / upgrade-downgrade UI, but emails reference "upgrade from Settings."
**Fix:**
- **(c) first, cheapest + highest value:** add `processed_stripe_events` table (`event_id` PK, `processed_at`). In `stripe_payments.py`'s webhook handler, check/insert the event ID before processing; skip if already seen. New Alembic migration.
- **(a):** add `elif event_type == "customer.subscription.updated":` handler — map `subscription["items"]["data"][0]["price"]["id"]` back to a plan via `PLANS` dict (reverse lookup by `price_id_attr`), update `user.subscription_plan` and `chases_limit` (do NOT reset `chases_used` — a tier change mid-cycle shouldn't wipe usage).
- **(b):** in `create_checkout_session`, look up `User` by email first; if they already have `subscription_status == "active"`, reject with a clear error directing them to the (new) billing portal instead of creating a duplicate checkout.
- **(e):** add a `GET /payments/portal` endpoint using `stripe.billing_portal.Session.create()`, link it from Settings page in frontend. Update `account_notifications.py`'s "upgrade from Settings" emails to link there once it exists (or soften the copy until then).
- **(d):** lower priority — add a scheduled job (daily, piggybacking on the existing sweep or separate) that lists active Stripe subscriptions via `stripe.Subscription.list()` and cross-checks against `User.subscription_status`/`stripe_subscription_id`, logging (and optionally auto-correcting) drift.
**Effort:** ~1.5 days total ((c)+(a)+(b) are the priority; (d) can follow after launch).

---

## HIGH (will break for real users soon)

### H1. Escalation/voice sweep crashes daily (timezone bug)
**Problem:** `escalation_started_at` / `last_reminder_sent` are naive `TIMESTAMP` columns; Postgres returns naive datetimes, but `scheduler.py` compares against `datetime.now(timezone.utc)` (aware) → `TypeError`, silently caught and logged per-step.
**Fix:**
- New Alembic migration: `ALTER COLUMN escalation_started_at TYPE TIMESTAMP WITH TIME ZONE`, same for `last_reminder_sent`, `subscription_started_at`, `sent_at` (reminder_log) — audit all `TIMESTAMP` columns in `src/models/*.py` and convert consistently.
- Update model definitions (`sa.TIMESTAMP(timezone=True)` instead of bare `sa.TIMESTAMP()`).
- Add a scheduler-specific test that actually exercises `run_escalation_sweep`/`run_voice_calls` against a Postgres-like timezone-aware column (SQLite in tests doesn't enforce this the same way — consider testing against the real Postgres URL in CI, or explicitly constructing aware datetimes in test fixtures to catch regressions).
**Do this together with C1** — fixing the crash without a "mark paid" button means voice/SMS escalation turns on and starts calling people who may have already paid.
**Effort:** ~0.5 day (migration + model fix + test).

### H2. Rate limiting installed but inert
**Problem:** `Limiter` is created in `app.py` but `SlowAPIMiddleware` is never added, no route has `@limiter.limit(...)`. Login/registration/checkout are unprotected.
**Fix:**
- `src/app.py`: `from slowapi import SlowAPIMiddleware` then `app.add_middleware(SlowAPIMiddleware)`.
- Add `@limiter.limit("5/minute")` to `/token` (`src/api/auth.py`), `@limiter.limit("3/minute")` to `/users/register`, `@limiter.limit("5/minute")` to `/payments/create-checkout-session`.
- Since Caddy proxies requests, confirm `get_remote_address` sees the real client IP — Caddy forwards `X-Forwarded-For` by default, but slowapi's default key func may need `X-Forwarded-For` parsing explicitly if it's reading `request.client.host` (which would be Caddy's internal IP). Verify with a test request and adjust `key_func` if needed.
**Effort:** ~0.5 day.

### H3. No per-invoice error isolation in SMS/voice loop
**Problem:** `scheduler.py`'s `run_sms_reminders`/`run_voice_calls` have one `db.commit()` at the end of the loop; a mid-loop exception loses earlier successful sends' state, causing duplicate sends next run.
**Fix:** wrap the body of each `for inv in ...` loop in try/except, commit after each successful invoice (mirroring how the email path already works per the audit). Log and continue on a single-invoice failure rather than letting it propagate.
**Effort:** ~0.25 day.

### H4. Sweep can silently skip / single point of failure
**Problem:** Advisory lock (`sweep_lock` in `scheduler.py`) can be left held on a pooled connection after a `db.commit()` returns it to the pool, causing future runs to see "lock not acquired." Also: single daily run at 08:00 UTC with no catch-up if the container was down at that moment; due-date comparisons use server UTC `date.today()`.
**Fix:**
- Since there's only one Hetzner instance, the distributed lock adds risk without benefit right now — remove `sweep_lock` entirely (simplify `run_daily_sweep` to not use it), OR fix it properly by using `pg_try_advisory_xact_lock` within a transaction that doesn't get its connection returned mid-use. Simplest: **remove it** since multi-instance isn't in play yet; re-add properly (with its own dedicated connection, not reused across commits) if/when you actually scale to >1 instance.
- Add a startup catch-up check: on app startup, check if today's sweep already ran (e.g. store `last_sweep_date` in a small table or just check if any invoice transitioned today); if not and it's past 08:00 UTC, run it immediately.
**Effort:** ~0.5 day.

### H5. Document upload links broken
**Problem:** `DocumentTable.tsx:104` builds `${window.location.origin}/api/documents/upload/<token>` — wrong domain (Vercel, not API), wrong path (no `/api` prefix on backend), no frontend page handles this route, and the backend endpoint doesn't accept a file upload at all (just marks submitted).
**Fix (pick one):**
- **Option A (ship it properly):** Build a public `/upload/:token` page in the frontend (no auth required) that calls `${API_BASE}/documents/upload/{token}` with `multipart/form-data`; update the backend endpoint in `src/api/document_request.py` to actually accept and store a file (needs file storage — local disk on Hetzner is simplest for now, or S3-compatible if available).
- **Option B (ship faster):** Hide the "Document Collection" feature from the UI/marketing until Option A is built — don't advertise a broken feature.
**Recommendation:** Option B now (quick, low-risk), Option A as a fast-follow if document collection is a feature you actually want to sell.
**Effort:** Option B: ~1 hour. Option A: ~1-2 days.

### H6. Admin-email bypass has no verification
**Problem:** Anyone can register with an email in `ADMIN_EMAILS` (or a paid `PendingSubscription` email) before its real owner does, stealing that access/plan.
**Fix (short-term, since this directly affects adding your own email):**
- Register your own account **immediately** after adding your email to `ADMIN_EMAILS` — close the window yourself.
**Fix (longer-term, do after critical items):**
- Add email verification on registration (send a confirmation link via Resend before activating the account), or
- Bind registration to the Stripe `session_id` passed to `/payment-success` instead of trusting a bare email match.
**Effort:** short-term: 5 minutes (just a process note). Long-term: ~1 day, can be deferred past initial launch.

### H7. No error tracking / alerting
**Problem:** Sweep failures, webhook failures, and crashes are invisible until a customer complains. `structlog.configure()` is never called (inconsistent log format). `webhooks.py` passes kwargs to a stdlib logger incorrectly, causing a 500 instead of 401 on bad GHL signatures.
**Fix:**
- Add Sentry: `pip install sentry-sdk`, initialize in `src/app.py` lifespan with `SENTRY_DSN` from settings (free tier is enough to start).
- Add an uptime monitor (UptimeRobot, free) pointed at `/health/ready` (after fixing M11 below) and `/health/live`.
- Fix `src/api/webhooks.py`'s logger calls to use structlog's kwarg-style logging consistently (`logger.error("event_name", key=value)` via structlog, not stdlib `logging.Logger.error(msg, key=value)` which doesn't accept arbitrary kwargs).
- Call `structlog.configure(...)` once at startup in `src/app.py` with a consistent processor chain (JSON renderer for prod, console for dev).
**Effort:** ~0.5 day.

---

## MEDIUM (fix before meaningful scale, not blocking initial launch)

| # | Issue | Fix direction | Est. |
|---|---|---|---|
| M1 | 4 tables (`pending_subscriptions`, `document_client`, `document_request`, `email_template`) never in Alembic, only `create_all()`. Missing `voice` in `Channel` enum. | Add a baseline migration capturing these tables' current schema exactly; remove reliance on `create_all()` in production startup (keep it dev-only, gated by `settings.environment == "development"`). | 0.5 day |
| M2 | GHL webhook signature check is optional; `ghl_webhook_signing_secret` can't actually be set via the settings API (`update_me` ignores it). | Make signature verification mandatory when a secret is configured; fix `UserSettingsUpdate`/`update_me` in `src/api/auth.py` to actually persist `ghl_webhook_signing_secret`. | 0.25 day |
| M3 | SMTP passwords stored + returned in plaintext via `GET /users/me`. | Strip `smtp_password` from the response model; encrypt at rest (e.g. `cryptography.fernet` with a key from settings) before storing, decrypt only when used to send. | 0.5 day |
| M4 | DB pool (10 + 20 overflow = 30 max) may exceed Supabase free-tier pooler limits (~15). | Set `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5` in Hetzner `.env`; confirm actual limit in Supabase dashboard. | 10 min |
| M5 | Supabase free tier: no backups, pauses after ~7 days inactivity. | Decide: upgrade to Supabase Pro ($25/mo) before real customers, or set up nightly `pg_dump` to off-site storage (e.g. a small cron job on Hetzner hitting the Supabase DB, uploading to S3/Backblaze). Recommend Pro — simpler and buys point-in-time recovery. | Decision + 1hr setup |
| M6 | Single Hetzner instance = SPOF, compounds with C5(d)/H4 gaps. | Covered by H7's uptime alert; document a manual restore/redeploy runbook (restore DB from Supabase backup, `git pull && docker compose up -d --build`). | 0.5 day (docs) |
| M7 | Admin/invite accounts never get usage reset (no Stripe subscription to trigger it). | In `src/services/account_notifications.py` or a small scheduled job, reset `chases_used` monthly for users with `subscription_plan` but no `stripe_subscription_id` (i.e., admin/invite grants), based on `subscription_started_at` day-of-month. | 0.5 day |
| M8 | 30-min token expiry, no refresh; logout doesn't call server; revocation list is in-memory (lost on restart). | Add a refresh-token flow, or extend expiry + add silent re-auth on 401 in frontend. Make `logout()` in `frontend/src/api/invoice.ts` call `POST /logout`. Move revocation to DB/Redis if this matters at current scale (likely low priority). | 1 day |
| M9 | Inconsistent frontend error handling: only Register.tsx handles 402; `pauseInvoice`/document calls don't handle 401; no React error boundary. | Add a shared `handleApiError()` helper used by all `invoice.ts` functions; add a top-level React error boundary component. | 0.5 day |
| M10 | Zero test coverage on `scheduler.py`, `debtor.py`, `invoice_create.py`, `document_*`, `webhooks.py`, `analytics.py`, cross-tenant isolation. | Add tests incrementally — prioritize scheduler (ties to H1/C4 fixes, should be tested as part of those) and a cross-tenant isolation test (user B cannot GET/PUT/DELETE user A's debtor/invoice IDs). | ongoing |
| M11 | `/health/ready` uses `Depends(lambda: next(get_db()))`, mishandling session lifetime. | Change to `Depends(get_db)` in `src/app.py:166`. | 10 min |

---

## LOW (polish, post-launch)

- Overdue invoices get SMS/voice but no overdue email (confirm this is intentional policy, not a gap).
- Invoices due exactly today (`status == due`) are never reminded — `reminder_service.py` only picks `upcoming`.
- Every route double-mounted (unversioned + `/api/v1`) — doubles attack surface/docs surface. Consider deprecating the unversioned routes once frontend is confirmed fully on one path.
- Confirm `VITE_API_BASE_URL` is set correctly in Vercel's dashboard for Production (can't verify from code alone).

---

## Suggested execution order

**Day 1 (fast wins + highest risk reduction):**
1. C2 (production mode + secret key) — 1 hr
2. M11 (health check fix) — 10 min
3. M4 (DB pool size) — 10 min
4. H2 (rate limiting) — 0.5 day
5. M2 partial (GHL signature mandatory) — included in H2 day

**Day 2-3 (stop active harm):**
6. C1 (mark paid) + H1 (timezone fix) together — these must ship together per the audit's own warning
7. C4 (subscription status checks in sweep) — 0.5 day
8. H3 (per-invoice error isolation) — 0.25 day
9. H4 (remove/fix sweep lock, add catch-up) — 0.5 day

**Day 4-5 (billing correctness):**
10. C5(c) event dedup — fold into other Stripe work
11. C5(a) subscription.updated handler
12. C5(b) duplicate-checkout prevention
13. C3 (per-tenant uniqueness) — can run parallel to Stripe work, different files

**Day 6 (observability + remaining high):**
14. H7 (Sentry + uptime monitor + logging fixes)
15. H5 (hide or fix document upload) — decide Option A vs B
16. H6 short-term (register your own admin email immediately once added)

**Week 2+ (medium/low, can overlap with onboarding first customers cautiously):**
17. M1, M3, M5 (schema baseline, SMTP encryption, backup strategy — M5 decision should happen before real customer data accumulates)
18. M6-M10 as capacity allows

---

## What's already solid (no action needed)
- Multi-tenant read isolation (every list/get endpoint scopes by `current_user.id`) — only the *uniqueness constraints* (C3) are cross-tenant, not reads/writes of existing data.
- Stripe webhook signature verification.
- Login/JWT mechanics (aside from the SECRET_KEY fallback in C2).
- Core usage-limit enforcement logic itself.

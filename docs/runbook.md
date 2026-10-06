# YourInboxHero Operations Runbook

This document provides operational guidelines, SLAs, and troubleshooting procedures for the YourInboxHero production environment.

## 1. Service Level Agreements (SLA)

| Metric | Target | Description |
|--------|--------|-------------|
| **Uptime** | 99.9% | Availability of the API and Dashboard. |
| **API Latency** | < 200ms | Average response time for data retrieval. |
| **Reminder Delivery** | < 5 mins | Time from scheduled trigger to email dispatch. |

### Escalation Matrix
- **Severity 1 (Critical Outage)**: Call on-call engineer immediately. (API down, DB unreachable)
- **Severity 2 (Degraded)**: Slack `#eng-alerts` and fix within 4 hours. (Reminders delayed, high 5xx errors)
- **Severity 3 (Minor Bug)**: Create Jira ticket. (UI glitch, isolated user error)

---

## 2. Deployment Procedures (Blue/Green)

The application uses Azure App Service slots for zero-downtime deployments.

### Automated Deployment
All merges to `master` automatically trigger the GitHub Actions workflow `deploy.yml`. This builds the Docker image and pushes it to the `green` slot.

### Manual Swap (Go-Live)
Once the `green` slot is verified, execute the swap to production:
```bash
az webapp deployment slot swap --resource-group yourinboxhero-rg-prod --name yourinboxhero-app-prod --slot green --target-slot production
```

### Rollback
If the production slot fails after swap, swap back immediately:
```bash
az webapp deployment slot swap --resource-group yourinboxhero-rg-prod --name yourinboxhero-app-prod --slot green --target-slot production
```

---

## 2b. Actual Deployment Target (Hetzner, not Azure)

Section 2 above describes an Azure App Service setup this project does not currently use. The
real production deployment is:

- **Backend**: a single Hetzner VPS (`188.245.24.60`), running the API and Postgres-adjacent
  services via Docker Compose, fronted by Caddy for TLS/reverse-proxy. There is no blue/green
  slot and no load balancer — this is a **single point of failure (SPOF)**: if this VPS is lost,
  the API, scheduler, and webhook endpoints are all down until a new server is provisioned.
- **Frontend**: deployed separately on Vercel (`yourinboxhero.com` / dashboard), independent of
  the Hetzner VPS's availability.
- **Database**: Supabase-hosted Postgres (free tier — no automatic backups or point-in-time
  recovery on this plan; see "Database Backup & Restore" below for the mitigation in place).

### Standard deploy (manual, no CI/CD pipeline exists yet)
```bash
ssh -i ~/.ssh/id_hetzner root@188.245.24.60
cd /root/YourInboxHero
git pull origin master
docker compose up -d --build
# wait for the API container to report healthy, then apply any new migrations:
docker exec yourinboxhero-api-1 python -m alembic upgrade head
```
Smoke-test after every deploy:
```bash
curl -s https://api.yourinboxhero.com/health/live
```

### Rollback
There are no deployment slots to swap. To roll back:
```bash
ssh -i ~/.ssh/id_hetzner root@188.245.24.60
cd /root/YourInboxHero
git log --oneline -5          # identify the last known-good commit
git checkout <commit-sha>
docker compose up -d --build
# if the bad deploy included a migration, you may need alembic downgrade -1
# (check alembic/versions/ for the specific revision before downgrading)
```

### Full server-loss disaster recovery (if the Hetzner VPS itself is destroyed/unreachable)
1. Provision a new Ubuntu VPS, install Docker + Docker Compose + Caddy.
2. Clone the repo: `git clone https://github.com/Stuti-1908/YourInboxHero.git /root/YourInboxHero`.
3. Recreate `/root/YourInboxHero/.env` from your password manager / secrets backup — this file is
   `.gitignore`d and is **not** in any backup described below. Losing it without a separate copy
   means regenerating `SECRET_KEY` (invalidates all existing JWTs — all users must re-login),
   the Fernet encryption key (any previously encrypted SMTP passwords / GHL webhook secrets stored
   in the DB become undecryptable and users must re-enter them), and all third-party API keys
   (Stripe, SMTP, GHL).
4. Point DNS (`api.yourinboxhero.com`) at the new server's IP once Caddy is up and has obtained a
   TLS cert.
5. Restore the database — see "Database Backup & Restore" immediately below. If the lost VPS also
   held the only copy of the `/root/YourInboxHero/backups/` directory, there is **no backup to
   restore from** except whatever currently exists on Supabase itself; this is the core risk of
   the current interim approach, see note at the end of that section.
6. `docker compose up -d --build`, then `docker exec ... alembic upgrade head`.
7. Smoke-test as above, then verify a scheduled reminder/chase actually fires on the next
   scheduler tick before considering the incident resolved.

### Database Backup & Restore (M5)

Nightly backups run automatically via cron on the Hetzner VPS itself:
```
0 2 * * * cd /root/YourInboxHero && ./scripts/backup_database.sh >> /var/log/yourinboxhero/backup.log 2>&1
```
- Backups are gzip'd `pg_dump` output, written to `/root/YourInboxHero/backups/`, retained 14 days
  (configurable via `RETENTION_DAYS` env var to the script).
- Check `/var/log/yourinboxhero/backup.log` to confirm the last run succeeded; the script exits
  non-zero and leaves no new file if `pg_dump` fails or produces a suspiciously small (<1KB) dump.

**To restore** (e.g. after a bad migration or accidental data deletion):
```bash
ssh -i ~/.ssh/id_hetzner root@188.245.24.60
cd /root/YourInboxHero
ls -lh backups/                          # pick the backup to restore
./scripts/restore_database.sh backups/yourinboxhero_<timestamp>.sql.gz
# type 'yes' when prompted — this OVERWRITES the current database contents
```
The script prints the masked target `DATABASE_URL` before prompting for confirmation — always
verify it's pointing at the intended database before typing `yes`.

**Known limitation (interim, not yet resolved):** these backups are stored on the same Hetzner
VPS the app runs on, which is *not* off-site. If that server is lost entirely, the backups are
lost with it — see step 5 of the disaster-recovery procedure above. This was an explicit,
accepted trade-off (self-managed nightly dumps instead of upgrading to Supabase Pro's managed
off-site backups) to avoid additional monthly cost; revisit moving backups to S3/Backblaze B2 or
upgrading the Supabase plan before this is the only backup a paying customer's data depends on.

---

## 3. Monitoring & Alerts

### Dashboards
Telemetry is collected via Azure Application Insights.
- **Failures**: View the "Failures" blade in App Insights to see exceptions.
- **Performance**: View the "Performance" blade to track API latency and dependency (PostgreSQL) bottlenecks.
- **Logs**: Query raw logs in Log Analytics:
  ```kusto
  AppTraces
  | where SeverityLevel >= 2
  | sort by TimeGenerated desc
  ```

### Active Alerts
- `api-http5xx-alert`: Triggers when Http5xx errors exceed 10 in a window. Check App Insights immediately.

---

## 4. Troubleshooting Guide

### Issue: "500 Internal Server Error" on all endpoints
**Possible Cause**: Database connection failure or App Service configuration missing.
**Resolution**:
1. Check App Insights "Failures" to see the exact stack trace.
2. Verify `DATABASE_URL` is set correctly in the Azure App Service configuration.
3. Ensure the PostgreSQL Flexible Server is running and the VNet integration is intact.

### Issue: Reminders are not sending
**Possible Cause**: SendGrid API key invalid, Azure Function timer failed, or Service Bus queue blocked.
**Resolution**:
1. Check Azure Functions logs in Log Analytics.
2. Check the `reminder-queue` in Azure Service Bus for dead-lettered messages.
3. Verify the SendGrid API key in Azure Key Vault.

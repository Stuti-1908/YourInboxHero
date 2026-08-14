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

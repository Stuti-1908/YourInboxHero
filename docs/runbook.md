# Operational Run-book

## 🚀 Deployment Process
1. **Terraform Apply**: 
   ```bash
   cd infra/terraform
   terraform apply -var "image_tag=<commit_sha>" -var "environment=production"
   ```
2. **Docker Build & Push**:
   ```bash
   docker build -t yourinboxheroacr.azurecr.io/yourinboxhero:<commit_sha> .
   docker push yourinboxheroacr.azurecr.io/yourinboxhero:<commit_sha>
   ```
3. **Slot Swap (Blue/Green)**:
   - Deploy new image to the `green` slot.
   - Run automated smoke tests (`/healthz` and `/api/invoice`) against the `green` slot URL.
   - Execute swap:
     ```bash
     az webapp deployment slot swap -g yourinboxhero-rg-production -n yourinboxhero-api-production --slot green --target-slot production
     ```

## ⏪ Rollback Procedure
If production fails post-swap, immediately swap back to the previous slot:
```bash
az webapp deployment slot swap -g yourinboxhero-rg-production -n yourinboxhero-api-production --slot green --target-slot production
```
Verify the production slot is healthy again.

## 🚨 Incident Response
- **Reminder Failures**: Check Azure Service Bus DLQ (Dead Letter Queue) and SendGrid logs. Review the `reminder_log` table for failure reasons.
- **Scheduler Issues**: Check Azure Monitor alerts. If scheduler duration > 2s, consider increasing the App Service plan tier or optimizing queries.

## 🩺 Health-Check
Endpoint: `GET /healthz` (To be implemented)
Returns JSON `{status: 'ok', uptime: <seconds>}`.

## 📞 On-Call Rotation
Refer to PagerDuty for the current on-call engineer.

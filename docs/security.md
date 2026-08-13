# Security Hardening Checklist

## 🔐 Implemented Security Measures

1. **Secrets Management** 
   - All secrets (SendGrid key, Service Bus connection, DB password) are stored in **Azure Key Vault**.
   - These are injected into Functions via Azure Managed Identity. No plaintext secrets exist in the codebase.
2. **Transport Encryption**
   - Azure App Service enforces HTTPS only (`https_only = true`).
3. **Data-At-Rest Encryption**
   - Enabled via Azure PostgreSQL Transparent Data Encryption (default for Flexible Server).
   - Key Vault has `enabled_for_disk_encryption = true`.
4. **Access Control (RBAC)**
   - App Service uses `SystemAssigned` Managed Identity to access Key Vault and Service Bus.
5. **Audit Logging**
   - `reminder_log` stores immutable JSON payloads for every sent reminder, retained for compliance.
6. **Vulnerability Scanning (CI/CD)**
   - Configured Trivy container image scanning.
   - Configured Bandit Python static analysis scanning.

## 📝 Pending Security Tasks
- **Pen-Test**: External provider runs before go-live; findings addressed before release.
- **GDPR Delete**: Need to implement `DELETE /debtor/{id}` endpoint that cascades to invoices and reminder logs (soft delete flag).
- **Network Isolation**: VNet integration for PostgreSQL Flexible Server to restrict public access.

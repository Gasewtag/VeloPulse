# VeloPulse Secrets Management & Production Security Guide

This document establishes the security guidelines, encryption policies, and secret management workflows for **VeloPulse**.

---

## 1. Classification of Secrets

| Category | Variables | Sensitivity | Storage / Vault Strategy |
| :--- | :--- | :--- | :--- |
| **Database Credentials** | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | High | Secret Manager / `.env` (chmod 600) |
| **Symmetric Encryption** | `ENCRYPTION_KEY`, `SECRET_KEY` | Critical | KMS / Vault (Min 32-byte Fernet key) |
| **Strava OAuth & Webhooks** | `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_VERIFY_TOKEN` | High | CI/CD Protected Secrets & Vault |
| **Telegram Bot** | `TELEGRAM_BOT_TOKEN` | High | CI/CD Protected Secrets & Vault |
| **Tunneling / Reverse Proxy** | `NGROK_AUTHTOKEN`, `ACME_EMAIL` | Medium | Injected via container runtime env |

---

## 2. Encryption at Rest (Fernet)

Strava athlete OAuth refresh tokens and sensitive tokens are encrypted using symmetric AES-128-CBC with HMAC-SHA256 authenticated encryption (`cryptography.fernet.Fernet`):

- **Generation**:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- **Configuration**:
  Store the output in `ENCRYPTION_KEY`. Never check this value into version control.
- **Key Rotation**:
  When rotating `ENCRYPTION_KEY`, use `Fernet.MultiFernet([new_key, old_key])` to decrypt legacy tokens and re-encrypt with the new primary key.

---

## 3. Secret Rotation Lifecycle

### 3.1. Database Password Rotation
1. Update `POSTGRES_PASSWORD` in production secrets store.
2. Alter the PostgreSQL user password:
   ```sql
   ALTER USER velopulse_user WITH PASSWORD 'new_secure_password';
   ```
3. Restart `api` and `worker` services to acquire updated pool connections:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --no-deps api worker
   ```

### 3.2. Telegram Bot Token Rotation
1. Request a new token via [@BotFather](https://t.me/BotFather) (`/revoke`).
2. Update `TELEGRAM_BOT_TOKEN` in the secrets store.
3. Restart the `bot` service:
   ```bash
   docker compose -f docker-compose.prod.yml restart bot
   ```

### 3.3. Strava OAuth Credentials Rotation
1. Regenerate `Client Secret` in the Strava Developer Dashboard.
2. Update `STRAVA_CLIENT_SECRET` in production environment.
3. Reload the API and worker containers.

---

## 4. Production Deployment Rules

- **Zero Secret In-Image Baking**:
  The `Dockerfile` and `Dockerfile.prod` never include `.env` or hardcoded tokens.
- **File System Permissions**:
  The runtime user in production is `appuser` (UID `10001`), which does not possess superuser privileges.
- **Automated Scanning**:
  Run pre-commit secret scanners (e.g. `detect-secrets`, `trufflehog`) in CI to prevent accidental credential commits.

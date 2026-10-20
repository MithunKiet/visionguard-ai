# Account security (Flow 5)

Account security in the navigation allows any signed-in user to enroll a TOTP authenticator after changing their initial temporary password. Existing non-MFA login remains compatible. MFA is opt-in; this release does not impose an enterprise-wide enrollment policy.

## Enrollment and login

1. Open **Account security**, enter your current account password and choose **Set up authenticator**.
2. Enter the private setup key in a compatible authenticator (TOTP, SHA-1, six digits, 30 seconds). The API also returns a standard provisioning URI. Do not send the key to support or place it in tickets/screenshots. The setup expires after ten minutes; restarting replaces the pending key.
3. Enter a current six-digit code and confirm. Enrollment and its security audit insert commit together. All prior access/refresh sessions expire. Wait for the next authenticator code, then sign in using email, password and code.
4. Disabling requires both the current password and a fresh authenticator code. It also expires all sessions.

Only setup responses contain the private key. Browser state holds it in memory while the page is open; the server sends `Cache-Control: no-store`. Neither tokens nor keys are stored in browser storage. The database stores encrypted pending/enrolled secrets. Replay protection uses a locked account row and the highest accepted time step, including concurrent requests. One adjacent step of clock skew is allowed. Enrollment and login share a per-user limit of ten MFA operations per five minutes; password login retains its separate throttle. Synchronize server and phone clocks. Redis failure fails authentication closed.

Login accepts optional `otp_code` on `POST /auth/login`; enabled accounts require it. No access token or refresh cookie is issued for missing/invalid/replayed codes. Refresh preserves verified-MFA state and checks the current password/security version. Live video and WebSocket authentication use the same current-account checks. Changing roles, status or factory scope continues to take effect from the database on subsequent authentication.

## Deployment and recovery

Apply migration **0025** before starting the new backend. Existing accounts without enrolled MFA continue to work; legacy rows marked MFA enabled without a secret remain blocked. Upgrade all API replicas together before allowing enrollment: old replicas cannot authenticate newly enrolled accounts.

`cryptography==50.0.2` is a pinned backend dependency. TOTP encryption uses a purpose-separated key derived from `JWT_SECRET`. Keep this existing secret stable, strong and securely backed up alongside the database; changing it makes enrolled/pending secrets unreadable and invalidates sessions. A future independent encryption-key rotation mechanism is not included. Test recovery before deployment.

Self-service recovery codes, administrator MFA resets and mandatory enrollment policies are not implemented. Do not enable MFA for an account without a recovery arrangement. A lost authenticator requires a deployment administrator to verify the person's identity through the company's approved process and perform a controlled database recovery: clear enrolled/pending secrets and counters, disable MFA, set a new random `auth_version`, and insert an attributed recovery audit record in the same transaction. Never clear MFA based solely on an email/chat request. Retain a securely controlled deployment recovery procedure; there is no remote recovery API in this release.

## Audit protection and remaining limits

Migration 0025 installs a PostgreSQL statement trigger rejecting UPDATE, DELETE and TRUNCATE of `audit.audit_log`, including statements matching zero rows. Inserts remain available. MFA setup/enable/disable insert their audit record in the same transaction as the change; an audit failure prevents that operation. The record contains no password, OTP or private key.

This guard does not protect against a privileged database owner/superuser disabling triggers or modifying schema. Deploy application connections with a separate non-owner role and controlled migrations; independently stored audit exports and retention/access policy remain deployment work. Existing non-MFA actions continue their existing best-effort audit contracts; this release does not claim complete durable audit coverage. Existing tenant, factory, role and first-password-change restrictions remain enforced and covered by regression checks.

## Validation

`tests/test_mfa.py` exercises real PostgreSQL/Redis enrollment, encrypted persistence, replay, concurrent login, refresh, session invalidation, expiry, throttling, atomic audit rollback and database mutation rejection. `tests/test_review_integration.py` covers current roles, suspension, tenant/factory scope, password/session revocation, live access and incomplete legacy MFA. Browser tests cover setup/code submission, private-key storage exclusion, session cleanup and unavailable-status gating. Authenticator hardware/phone recovery drills and production TLS/deployment remain outside these local tests.

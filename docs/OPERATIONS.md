# Operations guide

## Deploying
Run three Python processes from the same image and two Node processes:

| Process | Command |
|---|---|
| api | `gunicorn -c gunicorn.conf.py wsgi:app` (stateless; scale horizontally) |
| worker | `celery -A app.celery_app.celery worker -l info -c 4` |
| beat | `celery -A app.celery_app.celery beat -l info` (**exactly one** instance) |
| web / admin | `npm run start -w @crm/web` / `-w @crm/admin` |

Release order: build → `flask db upgrade` (one-off job, run as the schema **owner** role) → roll api/worker → roll web/admin. Migrations are additive; destructive changes ship in a later release.

**Database roles.** Use two roles in production: an *owner* that runs migrations and an *app* role (`NOSUPERUSER NOBYPASSRLS`) in `DATABASE_URL`. If the app ever connects as a superuser or `BYPASSRLS` role, tenant isolation silently degrades to application-level checks only.

**Put the admin app behind more than a login:** a separate hostname, an IP allow-list (`ADMIN_ALLOWED_IPS`) and/or VPN/SSO proxy. `ADMIN_REQUIRE_2FA` must stay on.

**Required environment for production:** `SECRET_KEY`, `JWT_SECRET`, `ADMIN_JWT_SECRET` (≥32 random chars, all different), `ENCRYPTION_KEY`, `COOKIE_SECURE=true`, a real `BILLING_PROVIDER`, `DATABASE_URL`, `REDIS_URL`, `WEB_ORIGIN`/`ADMIN_ORIGIN`/`API_ORIGIN`. The API will refuse to boot otherwise. Rotating `ENCRYPTION_KEY` requires re-encrypting stored integration tokens and TOTP secrets — plan a migration before you need one.

## Backups and disaster recovery
- **PostgreSQL:** enable continuous WAL archiving / PITR on your managed provider (target RPO ≤ 5 min) plus a nightly logical `pg_dump -Fc`. Retain 35 days; copy weekly dumps to a second region/account.
- **Object storage:** enable bucket versioning and a lifecycle rule that keeps non-current versions 30 days. Uploaded files are keyed by workspace id.
- **Redis** holds only rate-limit counters, caches and the Celery queue — losing it is an inconvenience, not data loss.
- **Restore drill (quarterly):** restore the latest dump into a scratch database, run `flask db current`, boot the API against it and open the demo workspace. Record the time taken; the target RTO is under 2 hours.
- **Deleted workspaces** are soft-deleted; data stays until an operator purges after the recovery window. Trial expiry never deletes data.
- **Customer data export** is self-service (Settings → Data) and works even for restricted/expired workspaces.

## Observability
- **Logs:** JSON lines on stdout in production (`LOG_FORMAT=json`), each with `request_id`; the same id is returned in the `X-Request-ID` header and in API error bodies, so a customer-reported error can be traced.
- **Errors:** set `SENTRY_DSN` (PII is not sent). 5xx responses are also written to `api_error_logs` and surface in *Super Admin → System health*.
- **Health:** `GET /healthz` for load balancers; *System health* shows DB, Redis, queue depth, provider modes, job runs, email failures, webhook failures, integration errors and suspicious auth events.
- **Alerts to configure on your platform:** API 5xx rate, p95 latency, queue depth > 500 for 10 min, any failed `billing_lifecycle` job, webhook failures > 0 for 15 min, DB connections > 80 %, disk, certificate expiry.
- **Audit:** every admin action and sensitive customer action lands in the append-only `audit_logs` table with actor, IP and before/after values.

## Scaling notes
Stateless API behind a load balancer; PgBouncer in transaction mode works because tenant context is set per transaction (`SET LOCAL`). Add read replicas for reports first. Scheduled emails, reminders, automation resumes and scheduled reports run through Celery; imports, exports and PDF reports currently run inside the request, so keep an eye on request time for very large workspaces and move them to Celery if needed.

## Runbooks
- **Customer locked out after payment issue:** Admin → Workspaces → *Extend trial* or *Extend period* (audit-logged), or *Change plan* for a complimentary assignment.
- **Suspected account takeover:** Admin → Users → *Suspend* (revokes all sessions immediately), then *Send password reset*.
- **Provider outage (email/AI/billing):** the System health page shows which provider is failing; failed emails are recorded with the provider error (there is no automatic retry yet — resend from the record or fix the provider and re-trigger), AI calls return a clear 502 "temporarily unavailable" message without consuming the customer's quota, and billing webhooks are idempotent so they can be replayed from the provider dashboard.
- **Rollback:** previous image + `flask db downgrade -1` only if the release shipped a migration; otherwise redeploy the previous image.

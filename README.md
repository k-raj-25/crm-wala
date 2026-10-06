# CRM Wala

A multi-tenant CRM SaaS for small businesses, agencies and sales teams — customer app, a completely separate Super Admin console, and a Flask API with database-enforced tenant isolation.

| App | Path | Port | Stack |
|---|---|---|---|
| Customer app + landing page | `apps/web` | 3000 | Next.js 16 · TypeScript · Tailwind v4 · Framer Motion · TanStack Query |
| Super Admin console | `apps/admin` | 3001 | Separate Next.js app, separate auth, separate cookies |
| Design system | `packages/ui` (`@crm/ui`) | – | Tokens, components, accessible primitives, charts (shared by both apps) |
| API | `backend` | 5000 | Flask 3 · SQLAlchemy 2 · Alembic · PostgreSQL 16 · Redis · Celery |

## Quick start

Needs Node 22+, Python 3.12+, PostgreSQL 16 and Redis. (Or `docker compose up --build` — see [Docker](#docker).)

```bash
make install                          # npm workspaces + python venv
psql -U postgres -f infra/postgres/init.sql   # creates the NON-superuser app role + databases
cp .env.example backend/.env          # defaults work for local development
make migrate                          # schema, RLS policies, plans, feature flags, email templates
make seed                             # demo workspace + 28 synthetic customers for the admin dashboards
make api                              # http://localhost:5000
make web                              # http://localhost:3000   (second terminal)
make admin                            # http://localhost:3001   (third terminal)
```

**Demo login (customer app):** `demo@demo.crmwala.dev` / `Demo@12345` (owner of "Acme Demo Co", in its 3-day trial).
Teammates: `priya@`, `rohit@`, `sneha@`, `vikram@demo.crmwala.dev` (manager / sales reps / viewer) with the same password.

**Super Admin:** create an account, then sign in at :3001. 2FA is mandatory; you scan a QR code on first sign-in.
```bash
cd backend && . .venv/bin/activate && FLASK_APP=wsgi.py flask admin create --email you@company.com --name "You" --generate
```

Run tests: `make test` (needs the `crm_test` database from `init.sql`). Typecheck: `make typecheck`. Production builds: `make build`.

## What's in the box

**Customer app** — leads (scoring, convert, public capture form), contacts, companies, deals, drag-and-drop Kanban pipeline with weighted values, tasks, calendar, unified activity timeline, notes/calls/meetings, email (templates, tracking pixel, inbound), files, import/export with column mapping and duplicate detection/merge, custom fields, tags, saved views, visual automation builder (triggers → conditions → actions, delays, test runs), AI assistant + insights (next-best-action, churn risk, data clean-up, pipeline diagnosis), reports (revenue, sales, conversion, pipeline, team, velocity, forecast… with CSV/PDF export and scheduling), team/roles/permissions, notifications, integrations marketplace, global search + ⌘K command palette, quick-create, dark mode, mobile bottom navigation, 5-step onboarding, trial/billing UX.

**Billing** — provider abstraction (`mock` for development, `stripe`, `razorpay`) feeding provider-neutral events into one idempotent state machine. Plans Starter ₹999 / Growth ₹2,499 / Business ₹5,999 / Enterprise (custom), monthly + annual, coupons, proration on upgrade, scheduled downgrades, cancel/resume, GST invoices (PDF), failed-payment grace period, restricted mode after grace. Trial: 3 days; after expiry data is **never deleted** — the workspace is read-only except billing and export.

**Super Admin** — platform dashboard (MRR/ARR, growth, churn, trial conversion), users and workspaces (extend trial, change plan, limit overrides, credits, suspend, delete — all behind typed confirmations + required reasons), impersonation (TOTP step-up, one-time 2-minute grant, bannered + audited session), plans/pricing/limits/features editor, coupons, payments + refunds, feature flags with per-workspace overrides, product analytics (DAU/WAU/MAU, funnel, AI usage), audit log with before/after diffs + CSV export, system health, platform settings (trial days, grace days, tax, signups, maintenance), email-template editor with preview and test-send, admin team with roles (superadmin / support / finance). Everything about pricing, limits and flags is data — no deploy needed.

## Architecture

```
Browser ── apps/web   (:3000) ──/api/*────────┐
Browser ── apps/admin (:3001) ──/admin-api/*──┤  Next rewrites ⇒ same-site cookies, no CORS
                                              ▼
                                   Flask API (:5000) ── PostgreSQL (RLS)  ── Redis ── Celery worker + beat
                                      │                                         └─ rate limits, cache
                                      ├─ S3-compatible object storage (local disk in dev)
                                      └─ providers: billing · AI · email  (swap via env)
```

### Multi-tenancy (defence in depth)
1. Every tenant table carries `workspace_id`.
2. **PostgreSQL row-level security** is `FORCE`d on 31 tables. Policies compare `workspace_id` to a transaction-local setting (`app.current_workspace_id`) that the API sets from the authenticated session. If it isn't set, queries return **zero rows** (fail closed). The app connects as a non-superuser role so RLS cannot be bypassed by mistake.
3. Foreign keys are validated *inside* the tenant (FK checks bypass RLS in Postgres, so `ensure_ref`/`ensure_member` verify them explicitly) — you cannot attach your deal to someone else's company by guessing a UUID.
4. The `protect(...)` decorator is the only way to expose a route: authentication → tenant binding → subscription state → RBAC permission → plan feature gate.
5. The frontend only ever holds one workspace's data; the admin app uses a different API prefix, token audience, signing key and cookie names.

### Security
Argon2id passwords · short-lived JWT access cookie + rotating server-side refresh sessions with **reuse detection** · CSRF double-submit (per realm) · account lockout · TOTP 2FA · admin IP allow-list · rate limits (Redis) · strict security headers · SSRF-safe webhook actions · upload type/size limits · secrets encrypted at rest (Fernet) · append-only audit log · password reset/verify links are signed, expiring and single-use. `Config.validate_for_production()` refuses to boot with dev secrets, `mock` billing, insecure cookies or admin without 2FA.

## Docker
`docker compose up --build` starts Postgres (non-superuser app role), Redis, MinIO (S3), migrations, API, Celery worker + beat, web and admin. Then `docker compose exec api flask seed-demo --reset`.
> **Verification status:** `docker-compose.yml` validates (`docker compose config`), but the images were **not built or run** in the environment this was developed in (no Docker daemon). Treat the Dockerfiles as a starting point and expect to tune them.

## What has and hasn't been verified

Verified in development (real PostgreSQL + Redis, headless Chromium):
- 20 backend tests: RLS fail-closed behaviour, cross-tenant API/FK isolation, RBAC, CSRF, lockout, reset single-use, 2FA, refresh reuse detection, admin/customer token separation, trial-expiry gating, coupons/proration/downgrade/cancel, import + dedupe + merge, automations (delays, SSRF block), AI metering, calendar feed.
- Both apps pass `tsc` and `next build`. Landing page, dashboard, lists, record pages, kanban drag-and-drop persistence, automation builder, billing + mock checkout, reports, AI, Super Admin login with 2FA enrolment, step-up re-verification, impersonation (banner shown in the customer app), suspend/extend-trial/coupon/settings flows were exercised end-to-end.

**Not exercised against live third parties** (code paths exist, but I had no credentials): Stripe and Razorpay checkout/webhooks/refunds, Google OAuth, Gmail/Outlook sync, WhatsApp/Slack/Zapier integrations, real SMTP/Resend delivery, S3 uploads, Anthropic/OpenAI models (the `mock` AI provider answers from real CRM data using the same tool layer). Integrations that need OAuth apps show as "sandbox" until credentials are configured.

**Placeholders to replace before launch:** landing-page testimonials and "trusted by" logos are illustrative copy, not real customers; legal pages, support email and pricing copy; the dev `ENCRYPTION_KEY` in `docker-compose.yml`. Load/performance testing, a third-party penetration test and full WCAG audit have not been done.

Deploying to Render: see [docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md) (`render.yaml` Blueprint).

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for deployment, backups/DR, observability and runbooks.

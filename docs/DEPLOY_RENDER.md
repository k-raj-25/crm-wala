# Deploying on Render

`render.yaml` at the repo root defines everything (a Blueprint). You do not create services by hand.

| Render resource | Purpose | Approx. cost* |
|---|---|---|
| `crm-web` (Node web service) | Customer app + proxies `/api/*` to the API | Starter ~$7/mo |
| `crm-admin` (Node web service) | Super Admin console | Starter ~$7/mo |
| `crm-api` (Python **private** service) | Flask API (not reachable from the internet) | Starter ~$7/mo |
| `crm-worker` (background worker) | Celery worker + scheduler (billing lifecycle, reminders, automations, scheduled emails) | Starter ~$7/mo |
| `crm-db` (Postgres 16) | Data | ~$6/mo and up |
| `crm-redis` (Key Value) | Rate limits, job queue | Free tier |

\*Check render.com/pricing. Roughly **$35-40/month** all-in. Free web instances sleep and can't run the private API/worker, and free Postgres is deleted after 30 days, so there is no truly free way to run this stack properly.

## 1. Prepare
1. Get the code onto GitHub (it is already at `k-raj-25/crm-wala`). Merge `claude/zealous-hamilton-vz3nn9` into `main`, or choose that branch when creating the Blueprint.
2. Generate the encryption key (used to encrypt 2FA secrets and integration tokens). Keep it safe; losing it makes stored secrets unreadable.
   ```
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   (Run it after `pip install cryptography`, e.g. inside `backend/.venv`.)

## 2. Create the Blueprint
1. Render dashboard > **New > Blueprint** > connect GitHub > pick the repo and branch.
2. Render reads `render.yaml` and lists the resources. It asks for the values marked `sync: false`:
   - `ENCRYPTION_KEY` - the key from step 1.
   - `WEB_ORIGIN` - the public URL of `crm-web`, e.g. `https://crm-web.onrender.com`.
   - `ADMIN_ORIGIN` - e.g. `https://crm-admin.onrender.com`.
   If you don't know the final URLs yet, enter your best guess and fix them in step 3.
3. Click **Apply**. The first build takes several minutes (the Next.js builds are the slow part; if a build runs out of memory, bump that service to a larger instance).

## 3. Fix the public URLs
After the first deploy open `crm-web` and `crm-admin` and copy their real `https://...onrender.com` URLs (they differ if the name was already taken). In **Environment Groups > crm-shared** set `WEB_ORIGIN` and `ADMIN_ORIGIN` to those values, then redeploy `crm-api` and `crm-worker`. These are used in email links, Google sign-in redirects and impersonation links.

## 4. Check tenant isolation is active (important, 1 minute)
Open `crm-db` > **Connect** > **PSQL command** (or a Shell on a paid instance) and run:
```sql
select rolname, rolsuper, rolbypassrls from pg_roles where rolname = current_user;
```
Both `rolsuper` and `rolbypassrls` must be **false**. Row-level security then applies to the app, because migrations and the app use the same owner role and the tables are `FORCE ROW LEVEL SECURITY`.

## 5. Create your first Super Admin
Open `crm-api` > **Shell** (available on paid instances) and run:
```
flask admin create --email you@yourcompany.com --name "Your Name" --generate
```
Copy the printed password. Then visit `https://<crm-admin>/login`, sign in, and scan the QR code with an authenticator app (2FA is mandatory).

Optional demo data on a staging deployment (never on production):
```
flask seed-demo --reset      # demo@demo.crmwala.dev / Demo@12345
flask seed-sample            # synthetic customers for the admin dashboards
```

## 6. Smoke test
- `https://<crm-web>` shows the landing page; sign up and finish onboarding.
- `https://<crm-admin>/system` shows database and Redis healthy, and recent jobs from the worker (wait ~10 minutes).
- Upgrade a test workspace through the **test checkout** (no real card needed while `BILLING_PROVIDER=mock`).

## 7. Going to production
The Blueprint ships as `APP_ENV=staging` so it boots with the mock payment provider. For real customers change these in **crm-shared** and then set `APP_ENV=production` (the API refuses to start in production with unsafe settings, listing what is missing):

| Setting | Value |
|---|---|
| `BILLING_PROVIDER` | `stripe` (with `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`) or `razorpay` (with `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`) |
| Webhook URL (in the provider dashboard) | `https://<your-web-domain>/api/v1/billing/webhooks/stripe` (or `/razorpay`) |
| `EMAIL_PROVIDER` | `resend` + `RESEND_API_KEY`, or `smtp` + `SMTP_HOST/PORT/USER/PASSWORD`; set `EMAIL_FROM` to an address on a verified domain |
| `STORAGE_BACKEND` | `s3` + `S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` (Cloudflare R2, AWS S3, etc.). Local disk is erased on each deploy |
| `AI_PROVIDER` | `anthropic` + `ANTHROPIC_API_KEY` (or `openai`); default `mock` answers from your data without a model |
| `GOOGLE_CLIENT_ID/SECRET` | Optional Google sign-in. Authorised redirect URI: `https://<your-web-domain>/api/v1/auth/google/callback` |
| `SENTRY_DSN` | Optional error tracking |

Then: add custom domains (`app.example.com`, `admin.example.com`) under each web service > Settings > Custom Domains, update `WEB_ORIGIN` / `ADMIN_ORIGIN`, and redeploy `crm-api` + `crm-worker`.

## Notes and gotchas
- **Why the API is private:** the apps proxy `/api` and `/admin-api` to it, which keeps cookies same-site (no CORS) and keeps the admin API off the public internet. `TRUSTED_PROXY_HOPS=2` tells the API to trust the Render load balancer *and* the Next.js proxy when reading client IPs; keep the API private or the header can be spoofed.
- **Restrict the admin console further** with `ADMIN_ALLOWED_IPS` (comma-separated). Note this checks the visitor's IP, so use fixed office/VPN addresses.
- **One worker only.** The worker embeds the scheduler (`-B`). Don't scale it above 1 instance; scale the API instead.
- **Migrations** run on every API start (`flask db upgrade`). With more than one API instance, move that to a Render *pre-deploy command* so only one process migrates.
- **Backups:** enable Postgres PITR / scheduled backups on a paid database plan, and follow `docs/OPERATIONS.md`.
- This blueprint was written against Render's documented Blueprint spec but **has not been deployed from this environment**; if Render's validator rejects a field name (plans and property names change), fix that line and re-sync.

# Deploying on Render

Two Blueprints are provided:

| File | Cost | Use for |
|---|---|---|
| `render.yaml` (default) | **Free** | Demos, trials, a first look |
| `render.paid.yaml` | ~$35-40/mo | Real customers (private API, always-on, background worker) |

## Free deployment

### What "free" means here
- **Sleeping:** free web services sleep after 15 minutes without traffic. The first visit afterwards takes ~30-60 seconds while they wake up.
- **Database expires:** Render's free Postgres is **deleted after 30 days**. Fine for a demo; for longer, upgrade it or point `DATABASE_URL` at another Postgres (see "Keeping data longer").
- **No worker/cron/shell:** background tasks run inline, and the periodic jobs (billing lifecycle, reminders, automations that wait, scheduled emails) are triggered every 15 minutes by a free **GitHub Actions** schedule that I added (`.github/workflows/jobs.yml`).
- **Emails are not sent** (`EMAIL_PROVIDER=console` prints them to the log), **payments are a test checkout** (`BILLING_PROVIDER=mock`), and **uploaded files are lost** when the service restarts (`STORAGE_BACKEND=local`). Everything else works.
- Free instances have 512 MB RAM and the Next.js builds are heavy. They worked on Render in testing only without a Node heap cap; if a build still fails with an out-of-memory error, see "If a build fails".

### Steps
1. **Merge to `main`** (or choose branch `claude/zealous-hamilton-vz3nn9` in Render). GitHub Actions only runs schedules from the default branch.
2. In Render: **New > Blueprint** > select the repo > Render shows `crmwala-db`, `crmwala-redis`, `crmwala-api`, `crmwala-web`, `crmwala-admin` - all on the **Free** plan, total **$0**.
   (If it still shows paid plans you are on `render.paid.yaml`; use the default `render.yaml`.)
3. Fill in the prompts (they depend on the final public URLs, which are `https://<service-name>.onrender.com` unless the name is already taken - if so, rename the services in `render.yaml` first, e.g. add your initials):

   | Variable | Value |
   |---|---|
   | `WEB_ORIGIN` (api) | `https://crmwala-web.onrender.com` |
   | `ADMIN_ORIGIN` (api) | `https://crmwala-admin.onrender.com` |
   | `ADMIN_BOOTSTRAP_EMAIL` (api) | your email - becomes the first Super Admin |
   | `ADMIN_BOOTSTRAP_PASSWORD` (api) | 12+ characters, letters and numbers |
   | `API_URL` (web **and** admin) | `https://crmwala-api.onrender.com` |

4. Click **Apply** and wait for the builds (5-10 minutes). The API runs migrations and creates your admin on start-up.
5. **Remove `ADMIN_BOOTSTRAP_PASSWORD`** from the `crmwala-api` environment (Dashboard > crmwala-api > Environment). It is only needed once.
6. Open `https://crmwala-admin.onrender.com/login`, sign in, and scan the QR code with an authenticator app (two-step verification is mandatory).
7. Open `https://crmwala-web.onrender.com`, sign up and try the product.
   Want sample data? Set `SEED_DEMO=true` on `crmwala-api` and redeploy; log in as `demo@demo.crmwala.dev` / `Demo@12345`. Staging only; switch it back to `false` for anything public.

### How email sending works
- **A user must verify their email before they can send.** Until then the compose box shows a "Verify your email" notice with a resend button, and the API refuses with `email_not_verified`.
- **Each user sends through their own mailbox.** Gmail/Outlook connections are personal (Integrations page); nobody can send through a teammate's account. Live Gmail/Outlook needs a Google/Microsoft OAuth app (`GOOGLE_CLIENT_ID/SECRET`); without it the connection runs in preview mode.
- **If the user hasn't connected a mailbox,** the email is sent by the platform as "*Their Name* via CRM Wala" with **Reply-To set to their own address**, so replies land in their inbox. This path needs a real provider: set `EMAIL_PROVIDER=resend` (+ `RESEND_API_KEY`, and `EMAIL_FROM` on a domain verified in Resend). It is not possible to send *as* an arbitrary @gmail.com address through a platform provider; mail providers reject that.
- `EMAIL_PROVIDER=console` (the default here) only writes emails to the API log.

### Turn on the periodic jobs (optional but recommended)
Without this, trial-ending emails, billing lifecycle and delayed automation steps never run.
1. Render > crmwala-api > Environment > copy the value of `JOBS_TOKEN`.
2. GitHub > your repo > Settings > Secrets and variables > Actions > **New repository secret**:
   - `API_URL` = `https://crmwala-api.onrender.com`
   - `JOBS_TOKEN` = the value you copied
3. GitHub > Actions > **periodic-jobs** > Run workflow once to test. It should finish green, and the admin **System health** page will list job runs.
   (GitHub pauses scheduled workflows after 60 days without repository activity; re-enable them in the Actions tab.)

### If a build fails
- **Out of memory on `crmwala-web`/`crmwala-admin`:** free builds have 512 MB. Either upgrade just that service to Starter ($7) for the build, or host the two Next.js apps on a free static/Next host such as Vercel or Cloudflare Pages (set `API_URL` to the API's public URL there) and keep only the API + database on Render.
- **API URL was wrong at build time:** the Next apps bake `API_URL` into the build. Fix the variable, then **Manual Deploy > Clear build cache & deploy**.
- **"Page not found" / network errors in the app:** check that `WEB_ORIGIN` and `ADMIN_ORIGIN` exactly match the public URLs (no trailing slash).

### Keeping data longer
Render's free database lasts 30 days. Options: upgrade it to a paid plan (~$6/mo), or use another free Postgres and paste its URL into `DATABASE_URL` on `crmwala-api`. **Important:** the app must connect as a role that does *not* bypass row-level security (that is what isolates customers). Run `select rolsuper, rolbypassrls from pg_roles where rolname = current_user;` - both must be `false`. Some providers' default roles bypass RLS (Neon's and Supabase's defaults do); create a dedicated role and database as in `infra/postgres/init.sql` instead.

### Going to production later
See "Going to production" in the paid section below, then move to `render.paid.yaml` (always-on, worker, private API).

---

## Paid topology (private API + worker)

`render.paid.yaml` defines this layout. In Render > New > Blueprint set **Blueprint file path** to `render.paid.yaml`.

| Render resource | Purpose | Approx. cost* |
|---|---|---|
| `crm-web` (Node web service) | Customer app + proxies `/api/*` to the API | Starter ~$7/mo |
| `crm-admin` (Node web service) | Super Admin console | Starter ~$7/mo |
| `crm-api` (Python **private** service) | Flask API (not reachable from the internet) | Starter ~$7/mo |
| `crm-worker` (background worker) | Celery worker + scheduler (billing lifecycle, reminders, automations, scheduled emails) | Starter ~$7/mo |
| `crm-db` (Postgres 16) | Data | ~$6/mo and up |
| `crm-redis` (Key Value) | Rate limits, job queue | Free tier |

\*Check render.com/pricing. Roughly **$35-40/month** all-in. Free web instances sleep and can't run the private API/worker, and free Postgres is deleted after 30 days, so there is no truly free way to run this stack properly.

### 1. Prepare
1. Get the code onto GitHub (it is already at `k-raj-25/crm-wala`). Merge `claude/zealous-hamilton-vz3nn9` into `main`, or choose that branch when creating the Blueprint.
2. Generate the encryption key (used to encrypt 2FA secrets and integration tokens). Keep it safe; losing it makes stored secrets unreadable.
   ```
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   (Run it after `pip install cryptography`, e.g. inside `backend/.venv`.)

### 2. Create the Blueprint
1. Render dashboard > **New > Blueprint** > connect GitHub > pick the repo and branch.
2. Render reads `render.yaml` and lists the resources. It asks for the values marked `sync: false`:
   - `ENCRYPTION_KEY` - the key from step 1.
   - `WEB_ORIGIN` - the public URL of `crm-web`, e.g. `https://crm-web.onrender.com`.
   - `ADMIN_ORIGIN` - e.g. `https://crm-admin.onrender.com`.
   If you don't know the final URLs yet, enter your best guess and fix them in step 3.
3. Click **Apply**. The first build takes several minutes (the Next.js builds are the slow part; if a build runs out of memory, bump that service to a larger instance).

### 3. Fix the public URLs
After the first deploy open `crm-web` and `crm-admin` and copy their real `https://...onrender.com` URLs (they differ if the name was already taken). In **Environment Groups > crm-shared** set `WEB_ORIGIN` and `ADMIN_ORIGIN` to those values, then redeploy `crm-api` and `crm-worker`. These are used in email links, Google sign-in redirects and impersonation links.

### 4. Check tenant isolation is active (important, 1 minute)
Open `crm-db` > **Connect** > **PSQL command** (or a Shell on a paid instance) and run:
```sql
select rolname, rolsuper, rolbypassrls from pg_roles where rolname = current_user;
```
Both `rolsuper` and `rolbypassrls` must be **false**. Row-level security then applies to the app, because migrations and the app use the same owner role and the tables are `FORCE ROW LEVEL SECURITY`.

### 5. Create your first Super Admin
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

### 6. Smoke test
- `https://<crm-web>` shows the landing page; sign up and finish onboarding.
- `https://<crm-admin>/system` shows database and Redis healthy, and recent jobs from the worker (wait ~10 minutes).
- Upgrade a test workspace through the **test checkout** (no real card needed while `BILLING_PROVIDER=mock`).

### 7. Going to production
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

### Notes and gotchas
- **Why the API is private:** the apps proxy `/api` and `/admin-api` to it, which keeps cookies same-site (no CORS) and keeps the admin API off the public internet. `TRUSTED_PROXY_HOPS=2` tells the API to trust the Render load balancer *and* the Next.js proxy when reading client IPs; keep the API private or the header can be spoofed.
- **Restrict the admin console further** with `ADMIN_ALLOWED_IPS` (comma-separated). Note this checks the visitor's IP, so use fixed office/VPN addresses.
- **One worker only.** The worker embeds the scheduler (`-B`). Don't scale it above 1 instance; scale the API instead.
- **Migrations** run on every API start (`flask db upgrade`). With more than one API instance, move that to a Render *pre-deploy command* so only one process migrates.
- **Backups:** enable Postgres PITR / scheduled backups on a paid database plan, and follow `docs/OPERATIONS.md`.
- This blueprint was written against Render's documented Blueprint spec but **has not been deployed from this environment**; if Render's validator rejects a field name (plans and property names change), fix that line and re-sync.

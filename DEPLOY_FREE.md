# Free deployment guide

## Optional Supabase research core

The Telegram webhook does not require a database to start. To enable the
point-in-time research core without adding another Railway service:

1. Create one Supabase project and apply migrations `001` through `005` in order.
2. Apply or re-apply `storage/supabase_roles.sql`, create separate login users, and grant
   Railway only `pasticuan_bot` while GitHub receives an ingest/validator user.
   In pooler URLs, use the login names (`pasticuan_bot_login.PROJECT_REF` and
   `pasticuan_jobs_login.PROJECT_REF`), not the NOLOGIN group-role names.
3. Put the read-only session-pooler URL in Railway as
   `SUPABASE_DATABASE_URL`. Never add `SUPABASE_WRITER_DATABASE_URL` to Railway.
4. Add the writer URL and optional `R2_*` values as GitHub Actions secrets.
5. Configure `data/source_manifest.json`, including a reviewed official
   `market_sessions_csv` when available. Merging it triggers ingestion.
6. Push through a pull request. Tests, Railway deployment, signed SHADOW
   publication, the LQ45 scan, and outcome evaluation then run automatically.
7. Use `/ready` to verify which snapshot the bot cached.

Supabase Free may pause an inactive project and does not provide downloadable
automatic backups. The bot therefore falls back to its bundled approved
snapshot, and the research workflow provides explicit `pg_dump` to R2 backup.

This repository is split into two independently deployable services:

- `railway.json` + `bot_webhook.py` + `Dockerfile`: Telegram webhook on
  Railway Free.
- `app.py` + `requirements.txt`: app on Streamlit Community Cloud.

Railway is the primary bot path when Render cannot accept your card. Railway's
current Free plan costs $0 and includes $1 of resource credit each month. New
accounts first receive a one-time $5 trial credit for up to 30 days, then revert
to the Free plan. A payment card is not needed to select Free, but Railway may
restrict outbound networking when it cannot verify a new account through
GitHub. The recurring $1 is a small allowance, not unlimited hosting, and plan
terms can change in the future.

## 1. Prepare GitHub and Telegram

1. Commit and push this repository to GitHub. The local `venv`, `.env`, and
   secrets are ignored and must not be committed.
2. In Telegram, open `@BotFather`, create a bot with `/newbot`, and retain its
   token privately.
3. Generate a webhook secret locally:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   Retain the output privately. Telegram webhook secrets may contain letters,
   digits, underscores, and hyphens.

## 2. Deploy the bot first on Railway Free

1. Sign in at <https://railway.com> using the GitHub account that owns the
   repository. Do not choose Hobby or add a payment method; keep the account on
   **Free**.
2. Choose **New Project > Deploy from GitHub repo**, authorize the repository,
   and select PastiCuan.
3. Railway detects the root `Dockerfile` and `railway.json`. Wait for the first
   build. It may initially fail because the required secrets have not been set.
4. Open the bot service, select **Variables**, and add:

   - `TELEGRAM_BOT_TOKEN`: the newly rotated BotFather token.
   - `TELEGRAM_WEBHOOK_SECRET`: the random secret generated in step 1.
   - `TELEGRAM_REQUEST_TIMEOUT`: `20`
   - `BOT_ENABLE_BACKTEST`: `false`
   - `BOT_SCAN_LIMIT`: `10`
   - `YAHOO_REQUEST_TIMEOUT`: `12`
   - `RESEARCH_SNAPSHOT_PATH`: `data/snapshots/latest.json.gz`
   - `SCAN_SNAPSHOT_TTL_SECONDS`: `300` (maximum accepted value is `900`)
   - `BOT_SNAPSHOT_ONLY`: `true`
   - `SNAPSHOT_ED25519_PUBLIC_KEY`: the base64 Ed25519 public key used by GitHub
   - `SUPABASE_DATABASE_URL`: optional read-only session-pooler URL
   - `AI_PROVIDER`: `off`

   Do not add `PORT`; Railway supplies it automatically. Do not add a database,
   volume, or object-storage service for the initial bot.
5. Redeploy if Railway does not do so automatically, then check **Deployments >
   View Logs** for startup errors.
6. Open **Settings > Networking > Public Networking** and click **Generate
   Domain**. Copy the resulting `https://...up.railway.app` URL.
7. Verify the health endpoint from your own terminal:

   ```bash
   curl -fsS https://YOUR_RAILWAY_DOMAIN/
   ```

   It should return `{"status":"ok","service":"pasticuan-telegram-webhook"}`.

8. Register the webhook from your own terminal:

   ```bash
   BOT_TOKEN="YOUR_NEW_BOTFATHER_TOKEN"
   WEBHOOK_SECRET="YOUR_GENERATED_WEBHOOK_SECRET"
   BOT_URL="https://YOUR_RAILWAY_DOMAIN"

   curl -fsS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
     --data-urlencode "url=${BOT_URL}/telegram/webhook" \
     --data-urlencode "secret_token=${WEBHOOK_SECRET}" \
     --data-urlencode "max_connections=1" \
     --data-urlencode 'allowed_updates=["message"]'

   curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
   unset BOT_TOKEN WEBHOOK_SECRET BOT_URL
   ```

9. Confirm that `getWebhookInfo` returns `"ok":true`, the Railway URL, and no
   `last_error_message`. Then send `/start`, `/ta BBCA`, and `/decision BBCA` to
   the bot.

### Normal deployment after initial setup

In Railway, open the bot service and verify **Settings → Source** points to this
GitHub repository, the deployment branch is `main`, and automatic deployments
are enabled. Railway Free does not require a scheduled deployment window.

For every later update, push a feature branch, open a pull request, wait for the
required `core-tests / test` check, and merge into `main`. The merge has two
independent automatic effects:

- Railway detects the new `main` commit and rebuilds/redeploys the Telegram bot.
- GitHub Actions starts `research-daily`; it publishes only verified signed
  snapshots and otherwise preserves the last valid production data.

Railway may become active before research finishes. This is safe because the bot
continues reading the last verified Supabase snapshot and refreshes its cache
within five minutes after a newer snapshot is published. Check Railway's
**Deployments** page, GitHub's **Actions → research-daily**, and then `/ready`,
`/status`, `/scan`, and `/ta BBCA`.

If Railway gives the account a **Limited Trial**, outbound calls to Telegram or
market-data providers may be blocked. Railway verification is automatic; the
practical no-card fallback in that case is to run `bot.py` on a computer you can
leave online, because most other managed hosts either require a card or offer
only time-limited compute.

### Optional alternative: Google Cloud Run

Cloud Run generally starts faster and scales more smoothly, but it requires a
billing account and its free allowance is not a hard spending cap. Use this only
if that trade-off is acceptable.

Install the Google Cloud CLI, create a project with billing enabled, and then:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
```

In Google Cloud Console, open **Security > Secret Manager** and create exactly
two secrets, each with one active version:

- `pasticuan-telegram-token`: the BotFather token.
- `pasticuan-webhook-secret`: the generated webhook secret.

Grant the Cloud Run runtime service account the **Secret Manager Secret
Accessor** role for those two secrets. Keeping only one active version of each
stays within Secret Manager's six-version free allowance.

From the repository root, deploy:

```bash
gcloud run deploy pasticuan-bot \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --min 0 \
  --max 1 \
  --cpu 1 \
  --memory 1Gi \
  --concurrency 1 \
  --timeout 300 \
  --set-env-vars BOT_ENABLE_BACKTEST=false,BOT_SCAN_LIMIT=5,RESEARCH_SNAPSHOT_PATH=data/snapshots/latest.json.gz \
  --set-secrets TELEGRAM_BOT_TOKEN=pasticuan-telegram-token:latest,TELEGRAM_WEBHOOK_SECRET=pasticuan-webhook-secret:latest
```

Cloud Run prints the HTTPS service URL. Verify it:

```bash
curl -fsS https://YOUR_CLOUD_RUN_URL/
```

It should return `{"status":"ok","service":"pasticuan-telegram-webhook"}`.

Register the webhook without writing either secret into the repository:

```bash
BOT_TOKEN="$(gcloud secrets versions access latest --secret=pasticuan-telegram-token)"
WEBHOOK_SECRET="$(gcloud secrets versions access latest --secret=pasticuan-webhook-secret)"
BOT_URL="$(gcloud run services describe pasticuan-bot --region=us-central1 --format='value(status.url)')"

curl -fsS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  --data-urlencode "url=${BOT_URL}/telegram/webhook" \
  --data-urlencode "secret_token=${WEBHOOK_SECRET}" \
  --data-urlencode "max_connections=1" \
  --data-urlencode 'allowed_updates=["message"]'

curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
unset BOT_TOKEN WEBHOOK_SECRET BOT_URL
```

Send `/start`, `/ta BBCA`, and `/decision BBCA` to the bot. The first request
after inactivity can be slower because the service scales from zero.

For local development, polling remains available:

```bash
TELEGRAM_BOT_TOKEN=... python bot.py
```

Do not run local polling while a webhook is registered. Telegram permits only
one delivery method at a time. To return to polling, call `deleteWebhook` first.

## 3. Deploy the app on Streamlit Community Cloud

1. Sign in at <https://share.streamlit.io> and choose **Create app**.
2. Select this GitHub repository and branch.
3. Set the entrypoint to `app.py` and Python to **3.12**.
4. In Advanced settings, add these secrets:

   ```toml
   AI_PROVIDER = "off"
   RESEARCH_SNAPSHOT_PATH = "data/snapshots/latest.json.gz"
   ```

5. Deploy. Community Cloud automatically installs the root
   `requirements.txt`; it does not install the heavier bot dependency file.

The app and bot currently use Yahoo as a clearly flagged fallback and therefore
remain `RESEARCH_ONLY`. They do not need PostgreSQL or object storage merely to
launch. Add Supabase and R2 only when enabling durable official-source ingestion.

## 4. Optional free persistence

For the point-in-time data pipeline:

1. Create a Supabase Free project.
2. Run all `.up.sql` files in `storage/migrations` in numeric order, then apply
   `storage/supabase_roles.sql` and create separate login users for the groups.
3. Create a Cloudflare R2 Standard bucket for original filings.
4. Put the read-only pooler URL in Railway. Put the writer database URL, R2
   credentials, and `BACKUP_ENCRYPTION_KEY` only in GitHub Actions secrets.
5. The weekly **idx-filings** workflow automatically selects the latest expected
   interim period and opens a manifest-only review PR. Review the tickers,
   timestamps, periods, and official URLs, then merge it. The merge downloads,
   validates, archives, and imports XBRL before requesting a research refresh.
   If IDX blocks discovery, copy the official `instance.zip` URLs into the same
   manifest and open a normal PR.
6. Add a reviewed official IDX session-calendar CSV to `data/source_manifest.json`.
   `SCHEDULED`, `COMPLETED`, and `HOLIDAY` rows make freshness holiday-aware;
   without it the pipeline deliberately uses a conservative weekday estimate.
7. Merge the implementation into `main` or manually dispatch **research-daily**
   once. It persists three-year OHLCV first, builds and gates a temporary
   candidate, signs and publishes SHADOW, publishes only a PRIMARY scan, and
   evaluates matured outcomes. Failed stages keep the last verified snapshots.
8. Normal operation is now push-and-merge only. The workflow also retries at
   19:00, 20:00, and 21:00 WIB. Formula changes must increment the checked-in
   release revision; database migrations and secret rotation remain manual.
9. Keep the model in `SHADOW` while history accumulates. The workflow records
   each candidate in `scan_signals` and evaluates matured 5/20/60/252-session
   outcomes. Run validation only after at least five years of point-in-time
   history and 24 holdout months exist; a deterministic rebuild, costs, delayed
   execution, drawdown, breadth, rank-IC confidence, and information-ratio gates
   must all pass before `VALIDATED_RESEARCH` is possible. Run the separate
   **research-validation** workflow for that evidence; it never auto-promotes.

Generate the Ed25519 key pair offline. Store the base64 private key only as the
GitHub Actions secret `SNAPSHOT_ED25519_PRIVATE_KEY`, and configure its public
counterpart plus a stable `SNAPSHOT_SIGNING_KEY_ID` in Railway. Never put the
private key in Railway or the repository. With a public key configured, invalid
or unsigned database snapshots fail closed.

For the initial August 2026 bootstrap, the reviewed membership seed is
`storage/seeds/2026-08-03_lq45_membership.sql`. Run it once in the Supabase SQL
Editor after migrations and role grants. It inserts the composition effective
3 August through 30 October 2026 and asserts that the period contains exactly
45 constituents. Placeholder issuer names/sectors are explicitly unclassified;
they must not be interpreted as official fundamental metadata.

The ingestion path supports strict canonical CSV layouts plus the reviewed IDX
XBRL concepts used by value and quality: parent net income, operating cash
flow, parent equity, cash, and basic EPS. TTM
flows correctly combine annual and cumulative interim comparisons. If official
period-end shares are absent, the factor dataset discloses use of the
weighted-average shares implied by official profit and EPS. Original PDFs can
be archived, but unrecognized PDF layouts remain quarantined.

R2 archival is optional for daily scan publication. An upload failure is
recorded in the signed SHADOW snapshot but does not discard a valid Supabase
scan. Database backups remain strict and fail when R2 upload is denied. For R2,
use an API token with Object Read & Write access scoped to the configured bucket.

## 5. Keep the deployment free

- On Railway, keep the subscription on **Free** and check monthly resource usage.
  The recurring credit is $1 and does not roll over.
- Keep only the bot service in the Railway project. A Railway PostgreSQL service
  would consume the same small monthly credit continuously.
- If using Cloud Run instead, keep minimum instances at `0`, maximum at `1`, and
  request-based billing. Never configure an always-on instance.
- Leave `BOT_ENABLE_BACKTEST=false` for interactive bot requests and keep
  `BOT_SCAN_LIMIT` small.
- Create a Google Cloud budget alert. A budget alert warns; it does not stop
  charges automatically.
- Keep only the latest container revisions/images. Artifact Registry includes
  limited free storage, and stale images accumulate after repeated deploys.
- Watch Cloud Run request time, outbound bandwidth, Secret Manager accesses,
  and Artifact Registry storage in Billing reports.
- Streamlit and Cloud Run filesystems are ephemeral. Never use local CSV or
  SQLite files as durable production storage.

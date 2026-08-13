# Free deployment guide

This repository is split into two independently deployable services:

- `bot_webhook.py` + `Dockerfile`: Telegram webhook on Google Cloud Run.
- `app.py` + `requirements.txt`: app on Streamlit Community Cloud.

This can cost USD 0 while usage remains inside each provider's free allowance.
Google Cloud requires a billing account and free quotas are not a hard spending
cap. Keep the limits below and configure billing alerts before sharing the bot.

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

## 2. Deploy the bot first on Cloud Run

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
  --set-env-vars BOT_ENABLE_BACKTEST=false,BOT_SCAN_LIMIT=5,MODEL_VALIDATED=false,SHADOW_COMPLETED_SESSIONS=0 \
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
   MODEL_VALIDATED = "false"
   SHADOW_COMPLETED_SESSIONS = "0"
   ```

5. Deploy. Community Cloud automatically installs the root
   `requirements.txt`; it does not install the heavier bot dependency file.

The app and bot currently use Yahoo as a clearly flagged fallback and therefore
remain `RESEARCH_ONLY`. They do not need PostgreSQL or object storage merely to
launch. Add Neon and R2 only when enabling durable official-filing ingestion.

## 4. Optional free persistence

For the point-in-time data pipeline:

1. Create a Neon Free PostgreSQL project.
2. Run `storage/migrations/001_point_in_time_schema.up.sql` against its pooled
   connection URL.
3. Create a Cloudflare R2 Standard bucket for original filings.
4. Store database/R2 credentials in Cloud Run Secret Manager and Streamlit's
   Secrets panel, never in `.env` or Git.

The current free limits are suitable for an initial LQ45 research dataset, but
the official filing ingestor still needs to be implemented before these stores
become authoritative inputs.

## 5. Keep the bill at zero

- Keep Cloud Run minimum instances at `0`, maximum at `1`, and request-based
  billing. Never configure an always-on instance.
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


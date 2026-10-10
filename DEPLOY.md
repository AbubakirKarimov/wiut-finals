# Deploying ComplianceRadar on Render (one Docker web service)

The API and the built frontend run in **one Docker container** (`Dockerfile`) as one Render
web service on the **free plan**, described by `render.yaml` (a Render Blueprint). The UI is
served by the API from the same origin, so no CORS setup is needed. No secret is stored in
the repository: every key below is typed into the Render dashboard.

## What the image does

- Stage 1 (`node:20-slim`) builds the frontend; stage 2 (`python:3.11-slim`) installs the
  backend, copies `backend/`, `data/` (pre-computed results, approved requirements, check
  hints, banks, regulations) and the built UI, and runs as a non-root user.
- Start command (Render sets `PORT`; the image defaults to 10000):
  `uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --proxy-headers --forwarded-allow-ips="*"`
  One worker, because jobs, the rate limiter and SQLite live in one process; proxy headers so
  the per-IP rate limit of `POST /check` sees the real client address.
- SQLite lives in `/tmp` (`DB_PATH=/tmp/compliance.sqlite`). With `RESET_DB_ON_START=1` every
  start rebuilds the state from `data/precomputed/findings.json` and
  `data/precomputed/decisions.json`. Decisions made on the site are labelled "live session,
  may reset on restart" (`LIVE_DECISIONS_EPHEMERAL=1`).
- `BROWSER_FALLBACK=0`: no Chromium in the image. JavaScript-only sites are reported as
  `not_checkable` ("page needs JavaScript rendering; not available on this hosted demo").
- The app starts and shows the pre-computed findings without any LLM key. Without a key,
  live checks still run the deterministic checks; LLM-assisted ones become `not_checkable`.

## Steps in Render (first deploy)

1. Sign in at https://dashboard.render.com with GitHub and allow access to the repository
   `AbubakirKarimov/wiut-finals`.
2. **New → Blueprint** → select the repository (branch `main`). Render reads `render.yaml`
   and shows one web service, `compliance-radar` (Docker, free, Frankfurt).
3. Render asks for the variables marked `sync: false`. Enter (or leave empty):

   | Variable | Value |
   |---|---|
   | `LLM_BASE_URL` | e.g. `https://api.groq.com/openai/v1` (any OpenAI-compatible endpoint) |
   | `LLM_API_KEY` | your provider key (secret) |
   | `LLM_MODEL` | a model id from your provider account |
   | `LLM_FALLBACK_1_BASE_URL` | optional second provider (used on HTTP 429 / network errors) |
   | `LLM_FALLBACK_1_API_KEY` | optional (secret) |
   | `LLM_FALLBACK_1_MODEL` | optional |
   | `LLM_TOKENS_PER_MINUTE` | optional client-side pacing, e.g. your provider's TPM limit |
   | `LLM_PRICE_INPUT_PER_MTOK`, `LLM_PRICE_OUTPUT_PER_MTOK` | optional list prices (USD per 1M tokens) for the cost metric; empty -> "not set" |

   All of them can be left empty: the demo then shows the pre-computed results only.
4. Click **Apply** (Deploy Blueprint). The first build takes a few minutes (frontend build
   + Python dependencies). When it is live, open `https://<service>.onrender.com/health`:
   it must return `{"status":"ok"}`. The app itself is at `https://<service>.onrender.com/`.
5. Check it from your machine:
   `python3 scripts/smoke_hosted.py https://<service>.onrender.com`
6. Put the URL into the README section "Hosted demo".

Later changes to secrets: Service → **Environment** → edit → **Save, rebuild and deploy**.

## Automatic deploys

`render.yaml` sets `autoDeployTrigger: checksPass`: after the first deploy, every push to
`main` is deployed **only after the GitHub CI checks pass** (`.github/workflows/ci.yml`:
backend tests, frontend lint and build). A failing CI run blocks the deploy.

## Free-plan behaviour

- The service **sleeps after about 15 minutes without traffic**. The next request wakes it;
  the first page then takes **about a minute** to open. Open the URL a minute before a demo.
- Optional: keep it awake during a demo window by pinging `/health` every 10 minutes (e.g.
  an external uptime monitor). `/health` answers from memory: no database, LLM or network.
- 512 MB memory; one instance; the filesystem is ephemeral (restarts reset live decisions,
  as the UI says).

## Local equivalent

```bash
docker build -t compliance-radar .
docker run --rm -e PORT=10000 -p 10000:10000 compliance-radar   # add -e LLM_API_KEY=... etc. if wanted
python3 scripts/smoke_hosted.py http://localhost:10000
```

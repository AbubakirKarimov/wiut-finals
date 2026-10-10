# Deployment checklist

Backend (FastAPI) → **Render**. Frontend (Vite build) → **Vercel**. GitHub Actions runs CI
on every push; `.github/workflows/deploy.yml` deploys both after CI passes on `main`.
No secret is stored in the repository: every key below is entered in a web dashboard.

## 1. Backend on Render

1. Sign in to https://render.com with GitHub.
2. **New → Blueprint**, pick the `AbubakirKarimov/wiut-finals` repository. Render reads
   `render.yaml` and proposes the web service `compliance-radar-api`. Click **Apply**.
3. Fill in the variables marked `sync: false` when Render asks (Service → **Environment**):

   | Variable | Value |
   |---|---|
   | `CORS_ORIGINS` | your Vercel URL from step 2, e.g. `https://wiut-finals.vercel.app` (fill after step 2; comma-separate several) |
   | `LLM_BASE_URL` | e.g. `https://api.groq.com/openai/v1` (any OpenAI-compatible endpoint) |
   | `LLM_API_KEY` | your provider key |
   | `LLM_MODEL` | a model id from your provider account |
   | `LLM_PRICE_INPUT_PER_MTOK`, `LLM_PRICE_OUTPUT_PER_MTOK` | USD per 1M tokens from the provider's price page; leave empty if unknown (metrics then say "not set") |

   Optional fallback provider: add `LLM_FALLBACK_1_BASE_URL`, `LLM_FALLBACK_1_API_KEY`,
   `LLM_FALLBACK_1_MODEL` (+ prices) the same way.
4. Wait for the first deploy, then open `https://<service>.onrender.com/health`; it must
   return `{"status":"ok"}`. This is the **public API URL**.
5. Service → **Settings → Deploy Hook** → copy the URL (it is a secret).

The start command already uses one worker and trusts the proxy headers, so the per-IP rate
limit sees the real client address:

```
uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers --forwarded-allow-ips="*"
```

`BROWSER_FALLBACK=0` on Render: JavaScript-only sites are reported as `not_checkable`
("needs browser") instead of launching Chromium.

## 2. Frontend on Vercel

1. Sign in to https://vercel.com with GitHub → **Add New → Project** → import the repository.
2. **Root Directory**: `frontend`. Framework preset: **Vite** (build `npm run build`,
   output `dist`).
3. **Environment Variables** (Production and Preview):
   `VITE_API_BASE_URL` = the public API URL from step 1.4 (no trailing slash).
4. Deploy, copy the production URL, and put it into Render's `CORS_ORIGINS` (step 1.3).
5. For deploys from GitHub Actions: Vercel → **Account Settings → Tokens** → create a token.
   Run `npx vercel@59.23.2 link` once inside `frontend/` (or open Project → Settings) to read
   the **Org ID** and **Project ID**.
   If you prefer Vercel's own Git integration, skip the `VERCEL_*` secrets: the deploy job
   then skips itself.

## 3. GitHub repository secrets

GitHub → repository → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | From |
|---|---|
| `RENDER_DEPLOY_HOOK_URL` | Render deploy hook (step 1.5) |
| `VERCEL_TOKEN` | Vercel token (step 2.5) |
| `VERCEL_ORG_ID` | Vercel org/team id (step 2.5) |
| `VERCEL_PROJECT_ID` | Vercel project id (step 2.5) |

Each deploy step is skipped while its secret is missing, so CI stays green before setup.

## 4. Approved requirements and stored results

- Checks run only for approved requirements. Approve them locally
  (`python -m backend.requirements.approve <clause_id> ...`), which writes
  `data/requirements.yaml`; commit that file. The API loads it into SQLite at startup.
- On Render's free plan the disk is **ephemeral**: findings, decisions and the LLM cache
  are lost on every redeploy or restart. For a persistent demo add a Render disk (paid) and
  set `DB_PATH` to a path on it, e.g. `/var/data/compliance.sqlite`.
- Pre-computed results: run `python scripts/crawl_all.py` where the database lives (Render
  **Shell** on a paid plan, or locally for a local demo). The UI labels those results
  "pre-computed on <time>"; nothing is shown that was not stored by a real run.

## 5. Smoke test after deploy

```bash
curl https://<service>.onrender.com/health
curl -X POST https://<service>.onrender.com/check -H 'Content-Type: application/json' \
     -d '{"url":"https://mkbank.uz/uz/"}'
curl https://<service>.onrender.com/jobs/<job_id>
```

Then open the Vercel URL → **Check** → enter a bank URL.

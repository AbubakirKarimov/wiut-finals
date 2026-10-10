# ComplianceRadar

A tool for the consumer-protection service of the Central Bank of Uzbekistan (CBU). It reads
banks' **public websites** and looks for **possible gaps** against CBU Regulation No. 3030
(minimum requirements for commercial banks in relations with consumers) and the Law
"On the State Language". Every finding carries evidence (page URL, a verbatim quote in the
original language, the law clause on lex.uz). Findings are never "violations": a CBU analyst
confirms or rejects each one, and every decision is logged.

Finding statuses: `ok` · `possible_gap` · `not_checkable`.

## Architecture

```
lex.uz (official texts) ──ingest──> data/regulations/*.json (clauses)
        │
        └─ shortlist (keywords + LLM) ─> data/requirements_review.md
                                          │  human approval (backend.requirements.approve)
                                          v
                               data/requirements.yaml ──> SQLite: requirements (approved)

bank URL ─> crawler (robots.txt, 1 req/s/host, depth 2, ≤15 pages, ≤60 s, PDF text)
              │  pages + language per page ──> SQLite: pages, runs
              v
           checks (approved requirements only)
              ├─ uz_version          deterministic: Uzbek vs Russian pages, language switcher
              ├─ required_document   keyword candidates -> LLM yes/no + quote
              └─ key_info            keyword candidates -> LLM yes/no + quote
              v
           quote verified verbatim in page text -> gating -> machine translation of quote
              v
           SQLite: findings ──> FastAPI ──> React UI (Check · Findings · Audit & Metrics)
                                   ^                         │
                                   └──── decisions (confirm / reject + comment)
```

| Path | What it does |
|---|---|
| `backend/ingest/lex.py` | Parses lex.uz pages into clauses (`data/regulations/`). |
| `backend/requirements/` | Shortlist of checkable clauses and the human approval CLI. |
| `backend/crawl/fetch.py` | Polite fetching: robots.txt (RFC 9309), Crawl-delay, per-host throttle, robots-checked redirects, size cap, plain Playwright renderer. |
| `backend/crawl/crawler.py` | Same-site crawler (HTML + PDF via pdfplumber), language versions first. |
| `backend/crawl/probe.py` | One-off reachability probe of all banks → `data/probe_report.md`. |
| `backend/checks/` | `uz_version`, `required_document`, `key_info`, quote verification, gating. |
| `backend/pipeline.py` | One site check: crawl → pages → checks → findings (a "run"). |
| `backend/llm/provider.py` | `OpenAICompatibleProvider` + `FallbackProvider`; SQLite cache and call log. |
| `backend/api/main.py` | REST API. |
| `backend/metrics.py` | Metrics from stored runs, LLM logs, decisions and team labels. |
| `frontend/` | React + Vite UI, Playwright e2e tests. |

### Decision rules (enforced in code, `backend/checks/runner.py`)

- Only requirements with `approved=true` are checked.
- An `ok` or `possible_gap` needs a quote that appears **verbatim** in the page text
  (whitespace-normalized; case, letters and punctuation must match, at least
  `CHECK_MIN_QUOTE_CHARS` characters). Otherwise the finding is `not_checkable`.
- An LLM answer whose quote is not found in the page is **rejected** (`not_checkable`).
- `possible_gap` requires at least `CHECK_MIN_PAGES_FOR_GAP` (5) pages read **and** no fetch
  errors (timeouts, 403/429/5xx, blocked); otherwise `not_checkable`. A 404 link is not a
  fetch error. Every finding stores `pages_read` and the list of URLs read.
- The English translation (`evidence_quote_en`) is produced **after** verification, is never
  used for verification, and is labelled "machine translation" in the API and UI.
- For an *absence* (`possible_gap`), the quote is context, not proof of absence: the closest
  related passage the LLM found (verified), or the keyword match / opening of the most
  relevant page read. The reason text says which.
- Crawl failures (blocked, unreachable, robots.txt disallow, needs browser) produce
  `not_checkable` with the reason; protection is never bypassed.

## How to run

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium     # only for BROWSER_FALLBACK=1
cp .env.example .env                                  # then fill LLM_* (optional)
.venv/bin/pytest                                      # backend tests

# API (one worker: jobs, rate limiter and SQLite live in one process)
.venv/bin/uvicorn backend.api.main:app --workers 1 --proxy-headers --forwarded-allow-ips="*"

# UI
cd frontend && npm install && npm run dev            # http://localhost:5173
npx playwright test                                   # e2e (starts its own servers)
```

`--reload` is fine for development; the deployed start command is the one above (see
`DEPLOY.md`), so the per-IP rate limit sees the client address behind the proxy.

### Pipeline commands

```bash
.venv/bin/python -m backend.ingest.lex                       # lex.uz -> data/regulations
.venv/bin/python -m backend.requirements.shortlist           # candidates for review (LLM)
.venv/bin/python -m backend.requirements.approve <clause_id> [...] [--check-type TYPE]
.venv/bin/python -m backend.crawl.probe                      # reachability -> data/probe_report.md
.venv/bin/python scripts/crawl_all.py [bank_id ...]          # crawl + check banks.yaml (batch runs)
```

### API

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | |
| GET | `/banks` | `data/banks.yaml` + latest run and finding counts |
| POST | `/check` `{url}` | public https URLs only; per-IP limit `CHECK_RATE_LIMIT_PER_MINUTE` → HTTP 429; returns `job_id` |
| GET | `/jobs/{id}` | status, progress, run, findings |
| GET | `/findings?bank_id=&status=&run_id=&latest=` | latest finished run per site by default |
| POST | `/decisions` `{finding_id, analyst, verdict, comment}` | verdict `confirmed` / `rejected` |
| GET | `/decisions` | decision log |
| GET | `/metrics` | latency p50/p95, tokens and cost per check, precision vs labels, analyst confirmation rate |

**CORS.** The API answers browser requests only from the origins in `CORS_ORIGINS`
(comma-separated `scheme://host[:port]`). When it is empty or unset, the local dev and e2e
origins are allowed: `http://localhost:5173`, `http://127.0.0.1:5173`,
`http://localhost:5174`, `http://127.0.0.1:5174`. In production set it to the hosted
frontend, e.g. `CORS_ORIGINS=https://wiut-finals.vercel.app` (then only the listed origins
are allowed). A `*` entry is refused at startup; credentials are not allowed cross-origin.

`POST /check` resolves the host and refuses non-public addresses; the same guard runs on every
redirect hop. `CHECK_ALLOW_PRIVATE_URLS=1` lifts this for local tests only.

### Configuration

All settings live in `.env` (template: `.env.example`); secrets are never committed. Crawl
caps: `CRAWLER_MAX_PAGES_PER_BANK`, `CRAWLER_MAX_DEPTH`, `CRAWLER_TIME_BUDGET_SECONDS`,
`CRAWLER_MIN_DELAY_SECONDS`, `BROWSER_FALLBACK`, `BROWSER_TIMEOUT_SECONDS`. Checks:
`CHECK_MIN_PAGES_FOR_GAP`, `CHECK_LLM_MAX_PAGES`, `CHECK_EXCERPT_CHARS`,
`CHECK_MIN_QUOTE_CHARS`, optional `UZ_VERSION_MIN_SHARE`. Search keywords for a requirement
can be written by a human in `data/check_hints.yaml`
(`requirements: {<requirement id>: {keywords: {uz_latn: [...], ru: [...]}}}`); otherwise the
LLM proposes them once and they are cached.

## Data sources and licences

- **lex.uz**: official texts of CBU Regulation No. 3030 (doc 3804290, Uzbek Cyrillic and
  Latin) and the Law "On the State Language" (doc 121051). Official legal documents are not
  objects of copyright in Uzbekistan. Sources and verification status: `data/sources.yaml`;
  parsed clauses: `data/regulations/`. Texts stay in the original language.
- **Bank websites**: only public pages, fetched with the User-Agent
  `ComplianceRadar/0.1 (...)`, robots.txt respected (RFC 9309: 4xx = no restrictions,
  5xx = disallow, unreadable = do not fetch), at most one request per second per host
  (higher if robots.txt sets Crawl-delay). Fetched pages are stored only in the local SQLite
  database with their fetch date and are **not committed** (`data/raw/` and `*.sqlite` are
  git-ignored). No personal data, card numbers or phone numbers are collected on purpose; the
  crawler skips login and search pages. Official URLs in `data/banks.yaml` were entered by
  the team, not guessed.
- **Test fixtures**: `frontend/e2e/fixture-site/` is a made-up Russian-only page set for tests.

## Models and their licences

No model is fixed in code. Any OpenAI-compatible endpoint works through `LLM_BASE_URL`,
`LLM_API_KEY`, `LLM_MODEL` (Groq, OpenRouter, Gemini's OpenAI-compatible API, a local Ollama),
with optional fallbacks on HTTP 429 / network errors. The licence and data terms are those of
the provider and model you configure; check them before sending page excerpts.
The LLM is used for: requirement shortlisting (offline), search keywords per requirement,
yes/no presence answers with a quote, and the machine translation of verified quotes.
`uz_version` uses no LLM.

Libraries: FastAPI (MIT), Uvicorn (BSD-3), httpx (BSD-3), Playwright (Apache-2.0),
BeautifulSoup4 (MIT), lxml (BSD-3), pdfplumber (MIT), pydantic (MIT), PyYAML (MIT),
python-dotenv (BSD-3), pytest (MIT), React (MIT), Vite (MIT).

## Cost model

Cost per check = Σ over API calls (input tokens × `LLM_PRICE_INPUT_PER_MTOK` + output tokens ×
`LLM_PRICE_OUTPUT_PER_MTOK`) / 10⁶. Token counts come from the provider's `usage` field and
are logged per call in `llm_calls` together with the run id. Cached responses (`llm_cache`,
key = hash of provider, model, prompt and schema) cost nothing and are counted separately.
If a price is not set, `/metrics` reports cost as "not set"; nothing is estimated.
Upper bound of LLM calls per check: per `required_document`/`key_info` requirement, one
keyword call (cached across runs), up to `CHECK_LLM_MAX_PAGES` presence calls, one
translation call.

## Known failure cases

- **JavaScript-only sites (`js_shell`)**: little or no text without a browser. With
  `BROWSER_FALLBACK=1` they are rendered in plain headless Chromium (network idle up to 45 s,
  one retry; otherwise `js_shell_failed`) and crawled to depth 1 only. On the hosted demo
  (`BROWSER_FALLBACK=0`) they are `not_checkable` with "needs browser". In the probe
  (`data/probe_report.md`) Agrobank and Hayot Bank needed the browser.
- **Blocked sites**: HTTP 403/429/503 or a challenge page ("Just a moment", captcha, ...) →
  `not_checkable`, never bypassed. Agrobank answers robots.txt with 403, which RFC 9309
  treats as "no restrictions".
- **Mixed-script text**: pages often mix Uzbek Latin, Uzbek Cyrillic and Russian (menus,
  footers). Page language is the dominant one by character and word counts, so a Russian page
  with a long Uzbek menu can be labelled wrongly. Some sites serve the same content under
  `/ru/` and `/uz/` (Hayot Bank's `/ru/` returned Uzbek text in the probe).
- **Apostrophes**: Uzbek Latin uses several apostrophe characters (ʻ ' ’). Quote verification
  is strict, so an LLM quote with a different apostrophe is rejected (`not_checkable`).
- **Scanned PDFs** have no text layer: stored as `readable=false`, not OCR'd.

## Honest limitations

- **Requirements must be approved by a human.** Until `data/requirements.yaml` exists, every
  check returns zero findings (the UI says so).
- The crawl reads at most 15 pages in 60 s on the demo; a missing document may simply be on
  an unread page. That is why `possible_gap` needs ≥ 5 pages and no fetch errors, and why
  each finding lists the URLs read.
- `uz_version` is site-level (any Uzbek page counts), not a per-page pairing of every key
  page.
- Precision is computed only from the team's labels in `data/labels/labels.csv`; without
  labels `/metrics` says "no data". The "analyst confirmation rate" comes from logged
  decisions only.
- Jobs run in the API process (one worker); a restart marks running jobs as failed. On
  Render's free plan the SQLite file is lost on redeploy (see `DEPLOY.md`).
- The DNS check of `POST /check` does not pin the resolved address (DNS rebinding is not
  covered).

## Built with an AI agent

The code, tests, workflows and documents in this repository were written with Claude Code
(an AI coding agent) under the team's direction; the team chose the banks and their URLs,
approves requirements, and labels results.

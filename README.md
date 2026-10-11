# ComplianceRadar

A tool for the consumer-protection service of the Central Bank of Uzbekistan (CBU). It reads
banks' **public websites** and looks for **possible gaps** against CBU Regulation No. 3030
(minimum requirements for commercial banks in relations with consumers) and the Law
"On the State Language". Every finding carries evidence (page URL, a verbatim quote in the
original language, the law clause on lex.uz). Findings are never "violations": a CBU analyst
confirms or rejects each one, and every decision is logged.

Finding statuses: `ok` · `possible_gap` · `not_checkable`.

**Mode: Partner product.** Owner: the Service for the Protection of Consumer Rights of
Banking Services, Central Bank of Uzbekistan. The partner bank is MKBANK (Mikrokreditbank).
The banks checked are the partner and the group fined by the CBU on 10 Nov 2025
([announcement](https://cbu.uz/en/press_center/news/3000256/), 18 banks); see
`data/banks.yaml`.

## Hosted demo

**URL: https://compliance-radar-vy9n.onrender.com** (one Docker service on
Render's free plan; see `DEPLOY.md`).

- **Pre-computed:** the Findings and Audit & Metrics screens show the latest batch run over
  the banks with a website URL (`data/precomputed/findings.json`, labelled "pre-computed on
  <date>") and the team's analyst decisions (`data/precomputed/decisions.json`).
- **Live:** the Check screen crawls any public https site and runs the checks while you
  wait. Decisions you make on the site are labelled "live session, may reset on restart":
  every restart rebuilds the state from the pre-computed files.
- **Sleeping:** on the free plan the service sleeps after about 15 minutes without traffic;
  the first request after that takes about a minute.
- **JavaScript-only sites** cannot be read there (no browser in the image):
  `not_checkable` "page needs JavaScript rendering; not available on this hosted demo".
  Agrobank and Hayot Bank need a browser; their pre-computed results come from a local run
  with the browser fallback.

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
  related passage the LLM found (verified) or the keyword match on the best candidate page.
  When no page matched the keywords at all, `evidence_quote` is empty, the reason starts
  "No evidence found on N pages read.", and a verified passage of the closest page is stored
  separately as `context_quote` (shown as "not evidence").
- `possible_gap` also needs at least one page of the requirement's site section (deposit,
  loan, document, ... from `data/check_hints.yaml`); otherwise `not_checkable` "relevant
  section not reached (read N pages)".
- Requirements that name the homepage (`location: homepage` in `data/check_hints.yaml`:
  main:49, main:51) take evidence from the home page; evidence found only on an inner page
  is `not_checkable`, not `ok`.
- Keywords match by word stems, across Latin/Cyrillic script, apostrophe variants and word
  order (`backend/checks/evidence.py`); quotes are still verified strictly.
- Crawl failures (blocked, unreachable, robots.txt disallow, needs browser) produce
  `not_checkable` with the reason; protection is never bypassed.

## How to run

Backend (Python 3.11) and frontend (Node 20) run separately in development. Settings are read
from `.env`; copy `.env.example` and fill in only what you need. The variable names are
listed in `.env.example` (LLM: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`,
`LLM_PRICE_INPUT_PER_MTOK`, `LLM_PRICE_OUTPUT_PER_MTOK`, optional `LLM_FALLBACK_1_*`;
crawler: `CRAWLER_*`, `BROWSER_FALLBACK`; API: `CHECK_RATE_LIMIT_PER_MINUTE`,
`CORS_ORIGINS`; storage: `DB_PATH`). Without LLM settings the checks that need the LLM end
`not_checkable`; everything else works.

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium     # only for BROWSER_FALLBACK=1
cp .env.example .env                                  # then fill LLM_* (optional)
.venv/bin/pytest                                      # backend tests

# API (one worker: jobs, rate limiter and SQLite live in one process)
.venv/bin/uvicorn backend.api.main:app --workers 1 --proxy-headers --forwarded-allow-ips="*"

# UI
cd frontend && npm install && npm run dev            # http://localhost:5173
npm run lint                                          # ESLint
npx playwright test                                   # e2e (starts its own servers)
```

Tests at submission (2026-10-11): `pytest` 264 passed + 1 expected failure (the documented
prompt-injection limitation, see below); Playwright e2e 21 passed (7 tests × 375, 768 and
1280 px). Hosted demo: https://compliance-radar-vy9n.onrender.com

CI (`.github/workflows/ci.yml`) runs the backend unit tests and the frontend lint and build
on a clean machine without `.env`, secrets, real LLM calls or real bank sites. The Playwright
e2e suite is run locally.

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

Real output of the shortlist run (2026-10-10, Groq `openai/gpt-oss-120b`):
`data/requirements_candidates.json` and `data/requirements_review.md`: 175 eligible clauses
→ 80 after the pre-filter → 36 shortlisted; 163 LLM API calls, 83 of them failed and were
retried (0 errors after retry), $0.036 total at list price.

### Batch run and pre-computed results

```bash
.venv/bin/python scripts/crawl_all.py            # all banks with a website_url
.venv/bin/python -m backend.precomputed export   # -> data/precomputed/findings.json
.venv/bin/python -m backend.team_decisions export   # team's analyst decisions -> decisions.json
```

At startup the API loads `findings.json` into an empty database and the team's decisions
from `data/precomputed/decisions.json` (idempotent). The Audit & Metrics screen shows "x of n
confirmed (reviewed by team on <date>)" from those decisions, or "not enough data" below 5.
Decisions made on the hosted demo are labelled "live session, may reset on restart"
(`LIVE_DECISIONS_EPHEMERAL=1` in `render.yaml`).

`crawl_all.py` prints progress and a summary table (pages, fetch errors, ok / possible gap /
not checkable, duration, LLM calls, cache hits, tokens, cost from `LLM_PRICE_*`) and writes it
to `data/precomputed/batch_summary.md`. A re-run is resumable: stored pages and cached LLM
answers are reused, so only the missing calls are made.
`findings.json` contains no page text: bank, requirement, status, reason, verified quote,
machine translation, evidence URL, URLs read, timestamps and model. At startup the API loads
it into an **empty** database (hosted demo); the UI labels those rows "pre-computed on <date>".
Live checks via `POST /check` work as before.

### Consistency metric

```bash
.venv/bin/python -m backend.consistency mkbank --runs 2
```

Run 1 is a normal check. Runs 2..N replay exactly the same pages and call the LLM again
under a fresh cache namespace (no cached answers), at temperature 0 and with `LLM_SEED` if
set. The command prints, per requirement, the statuses of each run and the share of run
pairs that agree on the status and on the evidence quote; `/metrics` and the Audit & Metrics
screen show the latest result per bank. Consistency runs never replace a bank's current
findings.

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

**CORS.** The hosted app serves the UI from the API's own origin, so it needs no CORS
setting. For a separately hosted frontend, the API answers browser requests only from the
origins in `CORS_ORIGINS`
(comma-separated `scheme://host[:port]`). When it is empty or unset, the local dev and e2e
origins are allowed: `http://localhost:5173`, `http://127.0.0.1:5173`,
`http://localhost:5174`, `http://127.0.0.1:5174`. For a separate frontend host, list
it, e.g. `CORS_ORIGINS=https://frontend.example` (then only the listed origins are
allowed). A `*` entry is refused at startup; credentials are not allowed cross-origin.

`POST /check` resolves the host and refuses non-public addresses; the same guard runs on every
redirect hop. `CHECK_ALLOW_PRIVATE_URLS=1` lifts this for local tests only.

### Configuration

All settings live in `.env` (template: `.env.example`); secrets are never committed. Crawl
caps: `CRAWLER_MAX_PAGES_PER_BANK`, `CRAWLER_MAX_DEPTH`, `CRAWLER_TIME_BUDGET_SECONDS`,
`CRAWLER_MIN_DELAY_SECONDS`, `BROWSER_FALLBACK`, `BROWSER_TIMEOUT_SECONDS`. Checks:
`CHECK_MIN_PAGES_FOR_GAP`, `CHECK_LLM_MAX_PAGES`, `CHECK_EXCERPT_WINDOW_CHARS`,
`CHECK_MAX_CONTEXT_TOKENS`, `CHECK_TIMEOUT_SECONDS`, `CHECK_RUN_BUDGET_SECONDS`,
`CHECK_MIN_QUOTE_CHARS`, optional `UZ_VERSION_MIN_SHARE`. LLM pacing: `LLM_MAX_OUTPUT_TOKENS`,
optional `LLM_REASONING_EFFORT`, `LLM_FALLBACK_AFTER_SECONDS`.

**Progress and resuming.** Each check prints progress (`check 3/9 <clause_id>: calling LLM
(attempt 2 ...)`, `rate limited, waiting 20 s`, tokens per call, `switching to fallback
model ...`) to the CLI and to `GET /jobs/{id}`. Pages are stored as they are fetched and
reused for `CRAWLER_CACHE_MAX_AGE_HOURS`; LLM answers come from `llm_cache`; each finding is
saved as soon as it is decided. A re-run after an interruption therefore continues quickly.
A check that runs out of time is `not_checkable` with "LLM timeout / rate limit". Search keywords for a requirement
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
- **cbu.uz**: the CBU announcement of 10 Nov 2025 on the monitoring of banks' websites
  (https://cbu.uz/en/press_center/news/3000256/), public; used only for the list of the 18
  fined banks in `data/banks.yaml`.
- **Pre-computed findings** (`data/precomputed/findings.json`, `batch_summary.md`): generated
  by this project's own pipeline on 2026-10-10 (`scripts/crawl_all.py`: crawl of each bank's
  public site with the limits above, then the approved checks; LLM `openai/gpt-oss-120b` on
  Groq for the LLM-assisted checks and translations; some checks re-run the same day with
  `scripts/recheck.py` after rule fixes, marked "re-checked" in the reason). They contain
  page URLs, short verbatim quotes and our reasons, not whole pages.
- **Analyst decisions** (`data/precomputed/decisions.json`): made by a team member after
  checking the banks' sites by hand.
- **No personal or confidential data** is used or stored: only public legal texts, public
  announcements and public bank web pages.
- **Test fixtures**: `frontend/e2e/fixture-site/` is a made-up Russian-only page set for tests.

## External services, models and their licences

No model is fixed in code. Any OpenAI-compatible endpoint works through `LLM_BASE_URL`,
`LLM_API_KEY`, `LLM_MODEL` (Groq, OpenRouter, Gemini's OpenAI-compatible API, a local Ollama),
with optional fallbacks on HTTP 429 / network errors. The licence and data terms are those of
the provider and model you configure; check them before sending page excerpts.
The LLM is used for: requirement shortlisting (offline), search keywords per requirement,
yes/no presence answers with a quote, and the machine translation of verified quotes.
`uz_version` uses no LLM.

- **Groq** (primary LLM, `openai/gpt-oss-120b`, Apache-2.0 open-weight model; Groq's terms
  of service apply to the API). Used for the pre-computed batch run; live checks on a
  server use it only if that server has an API key configured.
- **Google Gemini** (fallback, through its OpenAI-compatible API; Google's API terms apply).
  Supported as `LLM_FALLBACK_1_*`; it was **not** configured for the recorded batch run.
- **Render** (hosting of the demo, free plan).
- **Production** runs without any external API: a local model (e.g. through Ollama,
  `OLLAMA_BASE_URL`) and a local headless browser inside the regulator's perimeter.

Libraries: FastAPI (MIT), Uvicorn (BSD-3), httpx (BSD-3), Playwright (Apache-2.0),
BeautifulSoup4 (MIT), lxml (BSD-3), pdfplumber (MIT), pydantic (MIT), PyYAML (MIT),
python-dotenv (BSD-3), pytest (MIT), React (MIT), Vite (MIT), ESLint (MIT),
SQLite (public domain, through Python's `sqlite3`).

## Cost model

Measured on the pre-computed batch run (6 sites, 54 requirement checks, 2026-10-10;
`data/precomputed/batch_summary.md`), at Groq list price for `openai/gpt-oss-120b` taken from
`.env` ($0.15 input / $0.60 output per million tokens): **$0.0099 in total, about $0.0017 per
site check and $0.00018 per requirement check** (43 API calls, 32,862 tokens). Per-bank
figures: see `data/precomputed/batch_summary.md`.

- **LLM account:** Groq free tier. The audit hit its daily token quota (200,000 tokens per day,
  `eval/audit_report.md`) and the batch saw HTTP 429 rate limits, so the costs above are
  list-price equivalents, not money spent.
- **Hosting:** Render free plan (`render.yaml`: `plan: free`, region Frankfurt), $0.
- **Production:** a local model and a local browser; no per-call API cost.

How it is computed:

Cost per check = Σ over API calls (input tokens × `LLM_PRICE_INPUT_PER_MTOK` + output tokens ×
`LLM_PRICE_OUTPUT_PER_MTOK`) / 10⁶. Token counts come from the provider's `usage` field and
are logged per call in `llm_calls` together with the run id. Cached responses (`llm_cache`,
key = hash of provider, model, prompt and schema) cost nothing and are counted separately.
If a price is not set, `/metrics` reports cost as "not set"; nothing is estimated.
Upper bound of LLM calls per check: per `required_document`/`key_info` requirement, one
keyword call (cached across runs), up to `CHECK_LLM_MAX_PAGES` presence calls, one
translation call. Each call carries at most about `CHECK_MAX_CONTEXT_TOKENS` of page
passages, not whole pages.

## Known failure cases

- **JavaScript-only sites (`js_shell`)**: little or no text without a browser. With
  `BROWSER_FALLBACK=1` they are rendered in plain headless Chromium (network idle up to 45 s,
  one retry; otherwise `js_shell_failed`) and crawled to depth 1 only. On the hosted demo
  (`BROWSER_FALLBACK=0`) they are `not_checkable` with "page needs JavaScript rendering; not
  available on this hosted demo". In the probe
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

## Known limitations

- **JavaScript-only bank sites cannot be read on the hosted demo.** The hosted image has no
  browser, so a site whose home page has almost no text without JavaScript ends with every
  check `not_checkable` ("nothing was checked or guessed"). Home-page text measured over
  plain HTTP (`scripts/probe_hosted_examples.py`, `data/hosted_examples.json`, threshold
  1,500 characters from `data/check_hints.yaml`): Agrobank 0, Hayot Bank 0, Asakabank 0
  (JavaScript shells), Universal Bank 925 (too short to report gaps); MKBANK 13,139, Anor
  Bank 7,572 and Garant Bank 13,522 work. The Check screen offers only the working ones as
  examples. Pre-computed results for the others were made on a laptop with a local browser.
- **Jina Reader as an external renderer (tried, not enabled):** about 20 s per page, so a
  60 s run read only 2–5 pages of a JavaScript-only site (laptop: 4–11), and results were
  unstable between runs (Universal Bank's home page rendered in two runs and failed in the
  third; without a locale header it rendered the English site). Report:
  [`eval/jina_fallback.md`](eval/jina_fallback.md) (code on branch `jina-fallback`).
- **Chromium in a small container (tried, not enabled):** at 512 MB memory never ran out
  (peak 356 MiB). With 0.1 CPU every bank stopped after 1 page; with 0.5 CPU Agrobank read
  5 pages and Hayot Bank 3 (laptop: 4 and 11), Universal Bank 15. Image 2.06 GB unpacked.
  Report: [`eval/render_browser_experiment.md`](eval/render_browser_experiment.md) (code on
  branch `render-free-browser`).
- **Production design:** a local headless browser inside the regulator's perimeter
  (`BROWSER_FALLBACK=1`), no external rendering API.

- **Manual review is not system-wide precision.** The team reviewed 5 of the 11 possible
  gaps by hand: 2 confirmed, 3 rejected as false alarms (`data/precomputed/decisions.json`).
  That is a small sample chosen for review, not a precision estimate for the whole system.
  **6 possible gaps remain pending analyst review** (Anor Bank 14 and 37^5, Garant Bank
  37^5, MKBANK 37^5, Hayot Bank 18^1, Universal Bank 28^1).

## Honest limitations

- **Requirements must be approved by a human.** Until `data/requirements.yaml` exists, every
  check returns zero findings (the UI says so).
- The crawl reads at most 15 pages in 60 s on the demo; a missing document may simply be on
  an unread page. That is why `possible_gap` needs ≥ 5 pages and no fetch errors, and why
  each finding lists the URLs read.
- `uz_version` is site-level (any Uzbek page counts), not a per-page pairing of every key
  page.
- Precision of `possible_gap` is computed from analyst decisions (Confirm = correct,
  Reject = false positive; latest decision per finding) and from the team's labels in
  `data/labels/labels.csv`. Each value is shown with its count ("precision 62% on 13 decided
  findings"); below `METRICS_MIN_DECISIONS` (10) decisions it says "too few decisions to be
  meaningful". Without labels the label-based value is "no data".
- Jobs run in the API process (one worker); a restart marks running jobs as failed. On
  the hosted demo SQLite is in `/tmp` and rebuilt from `data/precomputed/` on every start
  (see `DEPLOY.md`).
- The DNS check of `POST /check` does not pin the resolved address (DNS rebinding is not
  covered).
- **Prompt injection is reduced, not solved.** Page text goes to the model inside an
  `<untrusted_page_text>` block marked as data, and a quote that repeats our own prompt
  instructions is rejected. A page that tells the model to answer "present" *and* contains
  the sentence it asks the model to quote would still pass verbatim verification (the quote
  really is on the page); `test_quote_planted_inside_injected_instruction_is_not_accepted`
  stays an expected failure to document this. An analyst's review remains the safeguard.

## Attribution

- Legal texts: lex.uz (official texts of Uzbekistan). Fined-bank list: cbu.uz announcement
  of 10 Nov 2025. Bank pages: the banks' own public websites.
- Libraries and services are used under the licences listed above. No code was copied from
  other projects.

## Built with an AI agent

The code, tests, workflows and documents in this repository were written with Claude Code
(an AI coding agent) under the team's direction; the team chose the banks and their URLs,
approves requirements, and labels results.

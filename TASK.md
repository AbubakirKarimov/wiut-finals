# TASK: ComplianceRadar (WIUT hackathon, FinTech track, Partner product mode)

The repository already exists; you are in its root (origin: AbubakirKarimov/wiut-finals,
branch main). Do not create a new repository. Commit and push after each stage and after any
meaningful change (small focused commits, tests pass first, never --force); see CLAUDE.md. Code, names, comments, UI, README,
finding texts, reports, LLM outputs and error messages are in English. Source data (laws,
bank websites) stays in its original Russian and Uzbek.

## 1. What we are building
A system for the Central Bank of Uzbekistan consumer-protection service. Every day it checks
banks' public websites against CBU Regulation No. 3030 ("minimum requirements for commercial
banks' activities in relations with consumers of banking services") and the Law "On the State
Language", and finds POSSIBLE GAPS with evidence. A CBU analyst confirms or rejects each
finding. Flow:
  lex.uz laws -> clauses -> requirements (approved by a human) -> bank website crawler ->
  checks -> findings with an evidence quote -> analyst decision -> decision log.

## 2. Hard rules (violation = project disqualification)
- No hardcoded answers, no mocks in place of working functions, no invented metrics or
  numbers. No data -> write "no data". LLM prices and any figures come from config or logs.
- A finding's status is only "possible_gap", never "violation". Not sure -> "not_checkable".
- Every finding has evidence: URL, verbatim quote, law clause id. The quote MUST appear
  verbatim in the page text (after whitespace normalization): verify this in code, otherwise
  the status is not_checkable.
- Evidence quotes stay in the original language (`evidence_quote`) and are verified as an
  exact match against the page text BEFORE any translation. A machine translation may be
  stored in `evidence_quote_en` (nullable); it is never used for verification, and the UI
  labels it "machine translation".
- Public pages only. Respect robots.txt, at most 1 request per second per domain, a
  User-Agent with the project name. Do not collect personal data, card numbers or phones.
- If a website or lex.uz blocks the bot, do NOT bypass the protection: record it in the
  report and ask the user.
- Secrets only in .env (there is a .env.example); they never get into code or commits.
- Before writing a stage's code, write a short plan. After a stage: run the tests, show the
  output, commit, give a 5-line report. Do not say "works" until you have run it.
- Places marked STOP: stop and wait for the user's answer.

## 3. Stack
Python 3.11, FastAPI, httpx, Playwright (chromium; run `playwright install chromium`),
BeautifulSoup4, pdfplumber, pydantic v2, SQLite, pytest, PyYAML. Frontend: React + Vite.
LLM only through the LLMProvider interface:
- `OpenAICompatibleProvider` — configured by `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` from
  .env; must work with Gemini, Groq, OpenRouter and Ollama (OpenAI-compatible endpoints)
  with no code changes.
- `FallbackProvider` — an ordered list of providers; on HTTP 429 or a network error it moves
  on to the next one.
- No model names or prices hardcoded anywhere.

## 4. Structure
CLAUDE.md, TASK.md, README.md, .env.example, data/{sources.yaml,banks.yaml,regulations/,raw/,
requirements.draft.yaml,requirements.yaml,labels/}, backend/{models.py,db.py,ingest/lex.py,
extract/requirements.py,crawl/crawler.py,checks/,llm/provider.py,api/main.py,tests/},
eval/run_eval.py, scripts/{check_sites.py,crawl_all.py,bench_local.py}, frontend/.
data/raw/ is in .gitignore. CLAUDE.md is built from section 2 of this file.

## 5. Data contract (backend/models.py, pydantic)
Requirement: id, text_original, text_en, source_doc, source_clause_id, source_url,
  check_type (uz_version | required_document | key_info), approved: bool.
Page: bank_id, url, language (uz_latn | uz_cyrl | ru | other), text, source_type (html | pdf),
  fetched_at, readable: bool.
Finding: id, bank_id, requirement_id, status (ok | possible_gap | not_checkable),
  evidence_url, evidence_quote (original language), evidence_quote_en (nullable, machine
  translation), confidence, created_at.
Decision: finding_id, analyst, verdict (confirmed | rejected), comment, decided_at.
Job: id, url, status, result_ref, error, created_at.
Everything is stored in SQLite (backend/db.py), plus the `llm_calls` log and the `llm_cache`.

## 6. Stages

STAGE A. Skeleton. Folder structure, requirements.txt, models.py, db.py, FastAPI with
 GET /health, a React placeholder page, pytest runs. Commit.

STAGE B. Laws from lex.uz.
 1. Read data/sources.yaml (the user fills in: doc_id, url, language, title). If the file
    does not exist, create a template and say what to fill in. Candidate to verify (not
    confirmed): lex.uz document 3593543 — confirm by its title that it is Regulation No. 3030,
    otherwise ask the user.
 2. Download ONE document (Russian version) into data/raw/ and describe its markup: which
    blocks correspond to clauses, where the LexUz editorial comments are, whether blocks have
    ids. STOP: wait for confirmation.
 3. After confirmation: backend/ingest/lex.py (CLI: python -m backend.ingest.lex --source <id>)
    parses saved pages offline (fetching is a separate polite function) into
    data/regulations/<source_id>.json: source_snapshot_date, annexes, clauses with a unique
    clause_id (<source>:<section>:<number>, e.g. cbu_reg_3030:resolution:1 vs
    cbu_reg_3030:main:1), chapter/paragraph/annex, block ids, lex.uz anchor link,
    text_original (canonical official text: Uzbek Cyrillic for Regulation 3030 and the State
    Language Law), text_parallel_latn (Uzbek Latin, blocks paired as '-' + id), amendment notes
    (raw text + amending act id such as 3030-10), repealed flag, kind (form annexes are
    kind=form). Editorial comments are dropped. Repealed clauses and form annexes are kept but
    excluded from requirement extraction. Tests run on small fixtures cut from real pages.

STAGE C. LLM layer and requirements.
 1. backend/llm/provider.py: complete_json(prompt, schema) -> dict; the response is validated
    with pydantic, one retry on error; each call logs input/output tokens, duration, provider,
    model and cache_hit into the llm_calls table. Implement OpenAICompatibleProvider and
    FallbackProvider as described in section 3. Tests with a substituted provider/transport.
 2. LLM response cache in SQLite (llm_cache), keyed by a hash of
    (provider, model, prompt, schema). A repeated request must not hit the API; the llm_calls
    row records that the response came from the cache.
 3. backend/extract/requirements.py: from data/regulations/*.json select the clauses relevant
    to a bank website (website, official website, state language, publication, disclosure and
    semantically close terms), turn each into a Requirement via LLMProvider: text_original is
    the clause text in its original language, text_en an English rendering. Write to
    data/requirements.draft.yaml with approved=false everywhere.
    STOP: the user manually approves 8-12 requirements and saves them in
    data/requirements.yaml.

STAGE D. Banks and crawler.
 1. data/banks.yaml: template (id, name, url, group: fined | control | partner). Fill in only
    the names: MKBANK (partner); Agrobank, Anor Bank, Hayot Bank, Universal Bank, Garant Bank,
    Asakabank, Turonbank, Infinbank, Trustbank, Madad Invest Bank, Saderat Bank, Orient Finans
    Bank, Ipoteka-bank, Tenge Bank, Ziraat Bank Uzbekistan, AVO Bank, Open Bank, TBC Bank,
    Davr Bank, Hamkorbank (fined). Do NOT guess website addresses: leave url empty.
    STOP: the user fills in urls and adds control banks.
 2. scripts/check_sites.py: for each bank opens the home page (httpx, 15 s timeout), writes to
    scripts/site_report.csv the response code, time, signs of bot protection, links to ru/uz
    versions, robots.txt. Sites that do not open without a browser are flagged separately.
 3. backend/crawl/crawler.py: crawl to depth 2-3 within the domain, page limit per bank in
    config, httpx, Playwright only if the page is empty. Page text, links to PDFs, PDF text
    (pdfplumber; a scan without text -> readable=false, guess nothing). Page language: lang
    attribute, characteristic letters (oʻ gʻ ў қ ҳ), frequent words. Cache in SQLite with date.
    scripts/crawl_all.py crawls every bank in banks.yaml.
 4. Run the crawl on ONE bank and show statistics (pages, PDFs, languages, errors).
    STOP: wait for the user's answer before crawling all banks.

STAGE E. Checks (backend/checks/, one module per type + a shared runner).
 - uz_version: key pages (loans, deposits, tariffs, terms) have an Uzbek version. No LLM; based
   on page languages and link pairs.
 - required_document: the required document or section exists on the site (keywords and
   headings, then LLM confirmation "yes/no" with a quote).
 - key_info: the information is present on the page (LLM answers strictly in JSON: present,
   quote; the quote is verified in code by the rule in section 2).
 - Quotes are verified in the original language first; only then may evidence_quote_en be
   filled with a machine translation.
 Tests on saved pages: one positive and one negative case per check.

STAGE F. API and UI.
 Backend: GET /banks; GET /banks/{id}/report; POST /check {url} -> job_id (check runs in the
 background, BackgroundTasks, status via GET /jobs/{id}); POST /findings/{id}/decision;
 GET /decisions. POST /check has a simple per-IP rate limit (value in config, e.g.
 CHECK_RATE_LIMIT_PER_MINUTE); exceeding it returns HTTP 429 with a clear message.
 Frontend (React, English): bank table with finding counters; report page: for each finding
 the requirement (English text, original on demand), status, original quote, the
 "machine translation" of the quote when present, link to the page and to the lex.uz clause,
 "confirm" and "reject" buttons with a comment; a "check a site by URL" field with progress;
 a decision log page. Works on real API data, no placeholders.

STAGE G. Metrics.
 eval/make_label_template.py creates data/labels/labels.csv from (bank, requirement) pairs with
 the system's preliminary answer in a separate column (not in the expected column).
 STOP: the team fills in expected (ok | possible_gap | not_checkable) by hand.
 eval/run_eval.py computes per check type the precision and recall for possible_gap, the false
 positive rate on labeled ok, the number of not_checkable, site check time, LLM cost from the
 token logs and the price in config (if there is no price, write "not set"); cache hits are
 reported separately and cost nothing. Output: eval/report.md with tables and a list of
 concrete errors. Too few labels -> say so, do not add labels yourself.

STAGE H. Robustness and deployment.
 Crawl results come from the cache; crawling only through scripts/crawl_all.py. POST /check:
 fast single-page check via httpx, Playwright behind a flag and with a timeout. Clear errors:
 site unavailable, bot protection, scan without text. scripts/bench_local.py runs 10 examples
 through OpenAICompatibleProvider pointed at Ollama and prints the average response time.
 Prepare deployment files (backend on Render or Railway, frontend on Vercel, GitHub Actions)
 and list which secrets the user must create. STOP: the user runs the deployment.

STAGE I. README (English).
 Fill in from facts: how to run, architecture (text diagram), data sources with licenses
 (lex.uz: official documents, not objects of copyright; bank sites: public pages, robots.txt
 respected, collection date), models and libraries used, which code was written with an AI
 agent, limitations and errors from eval/report.md. In a separate list, name everything that
 could not be confirmed by code or files.

## 7. Definition of done
Tests pass; the flow "bank -> finding with a quote -> analyst decision -> log" works on real
data; no hardcoded answers; metrics computed only from the team's labels; README describes what
is in the repository.

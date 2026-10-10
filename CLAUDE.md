# ComplianceRadar — agent rules

The full task is in `TASK.md`. Read it before starting any stage.

System for the Central Bank of Uzbekistan consumer-protection service: checks banks' public
websites against CBU Regulation No. 3030 and the Law "On the State Language" and finds
POSSIBLE GAPS with evidence. A CBU analyst makes the decision.

Language: code, names, comments, UI, README, finding texts, reports, LLM outputs and error
messages are in English. Source data (laws, bank websites) stays in Russian and Uzbek.

## Hard rules (violation = project disqualification)

- No hardcoded answers, no mocks in place of working functions, no invented metrics or
  numbers. No data -> write "no data". LLM prices and any figures come from config or logs.
- A finding's status is only `possible_gap`, never "violation". Not sure -> `not_checkable`.
- Every finding has evidence: URL, verbatim quote, law clause id. The quote MUST appear
  verbatim in the page text (after whitespace normalization): verify this in code, otherwise
  the status is `not_checkable`.
- `evidence_quote` stays in the original language and is verified against the page text
  BEFORE any translation. `evidence_quote_en` is a nullable machine translation, never used
  for verification; the UI labels it "machine translation".
- Public pages only. Respect robots.txt, at most 1 request per second per domain, a
  User-Agent with the project name. Do not collect personal data, card numbers or phones.
- If a website or lex.uz blocks the bot, do NOT bypass the protection: record it in the
  report and ask the user.
- Secrets only in `.env` (there is a `.env.example`); never in code or commits.
- Before writing a stage's code, write a short plan. After a stage: run the tests, show the
  output, commit, give a 5-line report. Do not say "works" until you have run it.
- Places marked STOP: stop and wait for the user's answer.

## Git workflow

- Remote: `origin` = https://github.com/AbubakirKarimov/wiut-finals.git, branch `main`.
- Commit and push at the end of every stage and after any meaningful change: small, focused
  commits with clear English messages (e.g. `feat(ingest): parse lex.uz clauses`).
- Run the tests before each commit; do not commit if they fail. `git push` right after.
- Never `--force`, never rewrite pushed history.
- Never commit secrets, API keys, `.env` or scraped bank pages (`data/raw/`).
- If push fails on authentication, do not work around it: stop and tell the user which
  credential is missing (gh auth login / token / SSH key).

## LLM

- Only through `LLMProvider`: `OpenAICompatibleProvider` (`LLM_BASE_URL`, `LLM_API_KEY`,
  `LLM_MODEL`) works with Gemini, Groq, OpenRouter and Ollama without code changes;
  `FallbackProvider` moves to the next provider on HTTP 429 or a network error.
- No model names or prices in code. Prices come from `.env`; missing price -> "not set".
- Responses are cached in SQLite (`llm_cache`, key = hash of provider, model, prompt, schema);
  a repeated request never hits the API, and `llm_calls.cache_hit` records it.

## API

- `POST /check` has a per-IP rate limit (`CHECK_RATE_LIMIT_PER_MINUTE`), HTTP 429 on excess.

## Stack

Python 3.11 (`.venv`), FastAPI, httpx, Playwright (chromium), BeautifulSoup4, pdfplumber,
pydantic v2, SQLite, pytest, PyYAML. Frontend: React + Vite.

## Commands

- Install: `python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- Tests: `.venv/bin/pytest`
- API: `.venv/bin/uvicorn backend.api.main:app --reload`
- Frontend: `cd frontend && npm install && npm run dev`

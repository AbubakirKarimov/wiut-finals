# Experiment: headless Chromium on a small Render-like container

Branch `render-free-browser` (not merged, not deployed). Date: 2026-10-11.

Setup: image with `playwright install --with-deps chromium`, `BROWSER_FALLBACK=1`,
`BROWSER_TIMEOUT_SECONDS=25`, `--disable-dev-shm-usage --disable-gpu`, images/fonts/media
blocked, one browser and one page at a time, context closed after each page,
`MAX_CONCURRENT_CHECKS=1`. Unchanged rules: robots.txt, 1 request/s per domain, 15-page
cap, 60 s per-run time budget (`CRAWLER_TIME_BUDGET_SECONDS` default).
LLM: no provider configured in the container (no `.env` in the image), so no LLM calls;
the two LLM-assisted checks (28^1, 37^5) can only end `not_checkable` in these runs.
Runs: `docker run --memory=512m --memory-swap=512m --cpus=<0.1|0.5>`, one bank at a time
through `POST /check`; memory sampled with `docker stats` every second.

Host: Apple Silicon (arm64, native image). Render runs amd64: CPU timings are indicative.

| CPUs | bank | total s | pages | decided of 9 | ok/gap/n.c. | peak MiB | OOM / restart |
|---|---|---|---|---|---|---|---|
| 0.1 | agrobank | 86.3 | 1 | 5 | 5/0/4 | 242 | no / 0 |
| 0.1 | hayot_bank | 86.3 | 1 | 2 | 2/0/7 | 274 | no / 0 |
| 0.1 | universal_bank | 95.6 | 1 | 2 | 2/0/7 | 275 | no / 0 |
| 0.5 | agrobank | 62.8 | 5 | 7 | 5/2/2 | 356 | no / 0 |
| 0.5 | hayot_bank | 63.9 | 3 | 4 | 4/0/5 | 323 | no / 0 |
| 0.5 | universal_bank | 24.6 | 15 | 7 | 2/5/2 | 291 | no / 0 |

Idle container: about 46 MiB. Cold start to healthy: 23.3 s at 0.1 CPU, 1.0 s at 0.5 CPU.
For reference, the stored pre-computed runs (laptop, browser, real LLM) read 4 / 11 / 15
pages for agrobank / hayot_bank / universal_bank.

Image: 2.06 GB unpacked (578 MB compressed), local build 120 s with `--no-cache`.

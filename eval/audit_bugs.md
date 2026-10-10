### Does the system lie? Short answer

- **Quotes are not invented.** All 27 audited quotes are verbatim in the stored page text and
  still on the live pages today (Part 1a/1b).
- **But some `possible_gap` findings are wrong.** Of 17 gaps, 4 have strong evidence on the
  site that the requirement is met (auditor's reading of keyword hits; to be confirmed
  manually), 2 more need a manual look, 1 hit was spurious. In 3 of the 4 strong cases the
  evidence is on pages the 15-page crawl never read; in 1 case (Anor Bank, restructuring
  procedure) the check read the page and missed it because of keyword matching (bug B1).
- **Some `ok` findings show the wrong evidence location.** For main:51 (phones on the
  homepage) and main:49 (complaint link on the homepage) the quote comes from an inner page.
  The audit found the numbers and the link on the homepage too, so the status is right but
  the evidence does not show what the requirement asks (bug B2).
- **Not measured:** LLM stability and most LLM controls. Groq's daily token quota (200,000
  TPD) was exhausted during the audit; no fallback provider is configured. These are
  reported as "not run", never as passed.

### Bugs found (as found by the audit; see "Fixes applied" below for what changed)

| # | Bug | Evidence in this audit | Proposed fix |
|---|---|---|---|
| B1 | Candidate pages are selected by **exact multi-word LLM keywords**; natural wording and even the literal required text never reach the LLM, and misspelled keywords ("gipergavola", "кфолатланган") are accepted. A gap is then reported without the LLM ever reading a page. | 3b: injecting "Omonatlaringiz kafolatlangan" (40^4) and a restructuring sentence (28^1) still gave possible_gap. 16 of 17 gaps were "no page matched the keywords". Anor 28^1: the restructuring-procedure document was on a page the check read. | Match keywords by word stems (all words of a keyword within a short window, prefix of ~5 letters, apostrophes unified); add human-reviewed keyword lists per requirement in `data/check_hints.yaml`; when nothing matches, send the 2 best pages by stem overlap to the LLM instead of declaring a gap, or report `not_checkable` ("no candidate page found"). |
| B2 | Location requirements are **not enforced**: requirements that name the homepage (main:51, main:49, main:17) accept evidence from any page. | 1c: main:51 and main:49 evidence URLs are inner pages; xfail test `test_homepage_requirement_rejects_evidence_from_inner_page`. | Add a `location` field to approved requirements (`homepage`, `deposit_page`, ...); restrict candidate pages to homepage-like URLs (site root and language roots) for `homepage`; otherwise the check may not return ok. |
| B3 | In browser mode a page that renders to an already-read URL is **stored twice**, inflating `pages_read` (which gates possible_gap). | 1d: Hayot Bank run lists 10 URLs, 9 unique. xfail test `test_browser_crawl_does_not_count_a_page_twice`. | In `_crawl_with_browser`, skip a render whose normalized final URL is already among the pages (same rule as the httpx path). |
| B4 | The page store keeps one row per (bank, URL): a later run **re-tags** the row and a re-fetch **overwrites** its text, so a run's page set and the exact text a quote was verified against are not preserved. | 1d: Agrobank batch run read 11 pages; only 1 row is still tagged with that run (two later POST /check jobs re-tagged them). 1a: 5 evidence pages were re-fetched by later runs (quotes still matched). | Add a `run_pages` table (run_id, url, sha256 of text) written at check time, keep page versions by (bank, url, sha256), and store the text hash on each finding so the quote can always be re-verified against the exact text. |
| B5 | **Prompt injection with a planted quote**: verification proves only that the quote is on the page. A page that tells the model to answer "present" and contains the planted sentence would pass. | Scripted xfail test `test_quote_planted_inside_injected_instruction_is_not_accepted`. Live test: the one variant that ran (quote not on the page) was refused by the model; the planted variant did not run (quota). | Before building excerpts, flag sentences addressed to an AI ("ignore previous instructions", "system note", "answer present", "quote exactly"); reject quotes that overlap a flagged sentence and mark the page for review. |
| B6 | For "no page matched" gaps the stored `evidence_quote` is the **opening navigation text** of the first page read. The UI labels it as context, but `findings.json` and the API present it as `evidence_quote`. | 16 of 17 gap quotes are menus ("Jismoniy shaxslarga Yuridik shaxslarga ..."). | Store it in a separate `context_quote` field and leave `evidence_quote` empty for absence findings. |
| B7 | `possible_gap` after **15 pages** misses sections that exist deeper in the site. | 3 of the 4 strong hits (Agrobank 18^1 and 40^4, MKBANK 40^4) are on deposit/loan pages the batch crawl did not read. | Decision for you (not applied): for requirements tied to a section (deposits, loans, documents), require that at least one page of that section was read before a gap is reported; otherwise `not_checkable`. |
| B8 | `uz_version` is `ok` as soon as one Uzbek page exists, even with a low Uzbek share; the quote is a menu. | Garant Bank: 2 Uzbek vs 9 Russian pages (18%) -> ok. | Decision for you: pair key pages (loans, deposits, tariffs) with their Uzbek counterparts, as TASK.md describes, or set `UZ_VERSION_MIN_SHARE`. Not changed by the audit. |

Data issue (not a code bug): the uncommitted change to `data/banks.yaml` sets Asakabank's
`website_url` to a Google Ads click URL (`...avtokredit-25?utm_source=...&gclid=...`), a
product page with tracking parameters, not the bank's home page.

Audit process note: a first version of `eval/audit.py` counted rate-limited controls as
"passed". This was caught and fixed before the report was written: such controls are now
"not run (LLM rate limit)".

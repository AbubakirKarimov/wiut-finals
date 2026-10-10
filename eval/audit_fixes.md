### Fixes applied after the audit

All numbers in this report were measured **before** these fixes and have not been
re-measured: the batch has not been re-run, stored findings and `data/precomputed/` are
unchanged, thresholds (15 pages, ≥5 pages for a gap) and approved requirements are unchanged.
No LLM calls were made while fixing (tests use a scripted provider).

| bug | commit | change | test |
|---|---|---|---|
| B1 | 4afdc89 | Keywords match by 5-letter word stems; case, apostrophes, punctuation and Cyrillic/Latin unified; words of a keyword in any order within 8 words. `data/check_hints.yaml` holds the cached LLM keywords for 40^4 and 49 with the misspellings fixed. | `test_required_link_text_reaches_the_llm` (xfail removed), `test_required_link_text_is_no_gap_with_reviewed_hints` |
| crawl order | fa726f5 | Within the same 15-page cap, deposit, loan, document, tariff and restructuring links are fetched first, then complaint and contacts, sections taking turns. robots.txt and 1 request/second unchanged. | `test_section_pages_fetched_first_within_page_cap` |
| B7 | c973291 | Decision applied: a `possible_gap` needs at least one page of the requirement's section (from `data/check_hints.yaml`); otherwise `not_checkable` "relevant section not reached (read N pages)". | 4 tests (`test_gap_without_section_page_is_not_checkable`, ...) |
| B6 | 5773f5e | "No page matched" gaps: `evidence_quote` empty; reason starts "No evidence found on N pages read."; `evidence_url` = closest page by keyword stems; a verified passage goes to the new `context_quote` field, labelled "not evidence" in the UI. | 2 tests |
| B2 | 7ad43ff | main:49 and main:51 (`location: homepage`): the home page goes to the LLM first; evidence found only on an inner page is `not_checkable`, not `ok`. | `test_homepage_requirement_rejects_evidence_from_inner_page` (xfail removed), `test_homepage_requirement_prefers_homepage_evidence` |
| B3 | e08466c | Browser mode skips a render whose URL was already read; the gap gate and `pages_read` count unique URLs. | `test_browser_crawl_does_not_count_a_page_twice` (xfail removed), `test_gap_gate_counts_unique_urls` |
| B5 | 7eed725 | Minimum only: page text sent inside `<untrusted_page_text>` marked as data; a quote that repeats our own instructions is rejected. **Not solved**: a planted quote still passes (README, "Honest limitations"). | `test_quote_planted_inside_injected_instruction_is_not_accepted` stays xfail; 3 new tests |
| B8 | 2fe87b7 | Decision applied: `uz_version` stays ok when an Uzbek version exists; the explanation says e.g. "2 Uzbek pages of 11; completeness not assessed". | 1 test |
| B4 | none | Not touched, as instructed (run history / page store). | |

Expected effect, not yet measured: fewer `possible_gap` findings for 18^1, 28^1 and 40^4
(more `ok` or `not_checkable` "relevant section not reached"), and more LLM calls per run
(more keyword candidates; main:49/51 always send the home page). Re-run the batch and repeat
Parts 2–4 to measure it.

# Jina Reader fallback (RENDER_FALLBACK=jina): measurement

Branch `jina-fallback`, 2026-10-11. Script: `eval/jina_fallback.py` (raw: `eval/jina_fallback.json`).

Settings as on the hosted demo: `BROWSER_FALLBACK=0`, `RENDER_FALLBACK=jina`, 15 pages,
60 s per run, 1 request/s per bank domain, Jina timeout 20 s, `X-Locale: uz-UZ`, no API key.
No LLM (`llm=None`): the LLM-path checks (28^1, 37^5) can only end `not_checkable` here,
while the stored laptop results used a local browser and the LLM. Throwaway database.

| bank | pages (Jina run) | pages (stored) | ok/gap/n.c. (Jina run) | ok/gap/n.c. (stored) | secs (Jina run) | secs (stored) | how pages were read |
|---|---|---|---|---|---|---|---|
| agrobank | 2 | 4 | 5/0/4 | 5/0/4 | 60.1 | 67.7 | jina: 2 |
| hayot_bank | 5 | 11 | 2/0/7 | 5/2/2 | 60.1 | 87.2 | jina: 5 |
| universal_bank | 15 | 15 | 1/3/5 | 2/5/2 | 20.7 | 12.4 | httpx: 15 |
| asakabank | 2 | no data | 2/0/7 | no data | 61.7 | no data | jina: 2 |

Asakabank has no stored laptop result (not in the 6-bank batch).

## Findings that differ from the stored results

| bank | requirement | stored | Jina run | Jina-run reason (start) |
|---|---|---|---|---|
| hayot_bank | main:14 | possible_gap | not_checkable | site had 2 fetch error(s), e.g. https://hayotbank.uz/main/individual/tariff: browser render failed: No evidence found on 5 pages read. Code checked li |
| hayot_bank | main:18^1 | possible_gap | not_checkable | site had 2 fetch error(s), e.g. https://hayotbank.uz/main/individual/tariff: browser render failed: No evidence found on 5 pages read. Code checked li |
| hayot_bank | main:37^5 | ok | not_checkable | site had 2 fetch error(s), e.g. https://hayotbank.uz/main/individual/tariff: browser render failed: No evidence found on 5 pages read. No page matched |
| hayot_bank | main:49 | ok | not_checkable | Code: "murojaat" appears in the text of https://hayotbank.uz/main/individual/home but not as a link the crawler could read (a button or script?); chec |
| hayot_bank | main:51 | ok | not_checkable | site had 2 fetch error(s), e.g. https://hayotbank.uz/main/individual/tariff: browser render failed: No evidence found on 5 pages read. Code checked fo |
| universal_bank | main:14 | possible_gap | not_checkable | homepage text too short (925 chars), likely dynamic content or blocked (threshold 1500, data/check_hints.yaml): No evidence found on 15 pages read. Co |
| universal_bank | main:17 | possible_gap | not_checkable | homepage text too short (925 chars), likely dynamic content or blocked (threshold 1500, data/check_hints.yaml): No evidence found on 15 pages read. Co |
| universal_bank | main:51 | ok | not_checkable | homepage text too short (925 chars), likely dynamic content or blocked (threshold 1500, data/check_hints.yaml): No evidence found on 15 pages read. Co |
| asakabank | main:14 | no data | not_checkable | only 2 page(s) read (at least 5 needed to report a possible gap): No evidence found on 2 pages read. Code checked links matching sayt xaritasi, sayt k |
| asakabank | main:17 | no data | not_checkable | Code: matching link "Bank haqida" found on https://asakabank.uz/uz/about-bank/bank-property, which is not a homepage page; the requirement names the h |
| asakabank | main:18^1 | no data | not_checkable | only 2 page(s) read (at least 5 needed to report a possible gap): No evidence found on 2 pages read. Code checked links matching kalkulyator, калькуля |
| asakabank | main:28^1 | no data | not_checkable | only 2 page(s) read (at least 5 needed to report a possible gap): No evidence found on 2 pages read. No page matched the keywords (keywords from hints |
| asakabank | main:37^5 | no data | not_checkable | only 2 page(s) read (at least 5 needed to report a possible gap): No evidence found on 2 pages read. No page matched the keywords (keywords from hints |
| asakabank | main:40^4 | no data | not_checkable | relevant section not reached (read 2 pages): no section page |
| asakabank | main:49 | no data | not_checkable | Code: matching link "Boshqaruv raisi murojaati" found on https://asakabank.uz/uz/about-bank/bank-property, which is not a homepage page; the requireme |
| asakabank | main:51 | no data | ok | Code: call-centre number +998 55) 514-41-08 found in the text of the homepage https://asakabank.uz/ru/. |
| asakabank | main:7 | no data | ok | Uzbek version present (2 Uzbek pages of 2; completeness not assessed): 2 Uzbek and 0 Russian pages of 2 HTML pages read (Uzbek share 100%); language s |

## Observations from earlier runs of the same script (same day)

- Run 1 (before `X-Locale`): Jina rendered universalbank.uz in English, the crawler then
  followed only `/en/` links and `main:7` became `not_checkable` ("no Uzbek or Russian
  pages among 15"). `X-Locale: uz-UZ` was added after this.
- Universal Bank's home page re-render through Jina succeeded in runs 1 and 2 (925 -> 4,308
  characters) but failed in run 3 (above): results are not stable between runs.
- Pages read by Jina per 60 s run: agrobank 2–3, hayot_bank 3–7, asakabank 2–4.
- Asakabank `main:51`: the quote "+998 55) 514-41-08" is verbatim from Jina's Markdown
  rendering, which differs in punctuation from what a browser shows.

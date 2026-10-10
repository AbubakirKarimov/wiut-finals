# Batch run summary

- Finished: 2026-10-10 19:57 UTC
- Model: openai-compatible:api.groq.com / openai/gpt-oss-120b
- Cost: token logs x LLM_PRICE_* from .env
- Not run (no website_url): turonbank, infinbank, trustbank, madad_invest_bank, saderat_bank, orient_finans_bank, ipoteka_bank, tenge_bank, ziraat_bank_uzbekistan, avo_bank, open_bank, tbc_bank, davr_bank, hamkorbank
- Not selected for this run (have a website_url): asakabank
- Columns: by code / LLM-assisted = who decided each finding's status; $/check = cost / requirement checks

| bank | crawl | pages | errors | ok | gap | n/c | by code | LLM-assisted | secs | calls | cached | 429/err | tokens | cost $ | $/check |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mkbank | ok | 15 | 0 | 8 | 1 | 0 | 8 | 1 | 16.4 | 7 | 1 | 0 | 6217 | 0.0022 | 0.000243 |
| agrobank | ok | 4 | 0 | 5 | 0 | 4 | 8 | 1 | 67.7 | 6 | 1 | 0 | 4542 | 0.0013 | 0.000143 |
| anor_bank | ok | 15 | 0 | 5 | 2 | 2 | 8 | 1 | 12.8 | 5 | 1 | 0 | 5370 | 0.0014 | 0.000153 |
| hayot_bank | ok | 11 | 0 | 5 | 2 | 2 | 7 | 2 | 87.2 | 11 | 0 | 2 | 10660 | 0.0030 | 0.000334 |
| universal_bank | ok | 15 | 0 | 2 | 5 | 2 | 9 | 0 | 12.4 | 2 | 0 | 0 | 1281 | 0.0006 | 0.000062 |
| garant_bank | ok | 15 | 0 | 6 | 1 | 2 | 8 | 1 | 87.9 | 12 | 0 | 5 | 4792 | 0.0015 | 0.000162 |
| TOTAL | 6 ok | 75 | 0 | 31 | 11 | 12 | 48 | 6 | 284.4 | 43 | 3 | 7 | 32862 | 0.0099 | 0.000183 |

LLM calls by purpose (presence decides a status; translation only translates a verified quote):

| purpose | API calls | cache hits | tokens |
|---|---|---|---|
| failed | 1 | 0 | 0 |
| presence (decision) | 9 | 0 | 19954 |
| translation | 33 | 3 | 12908 |

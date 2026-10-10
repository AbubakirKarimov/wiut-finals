# Bank website probe

- Run at: 2026-10-10 13:19 UTC
- User-Agent: `ComplianceRadar/0.1 (WIUT hackathon; consumer-protection research bot)`
- Min visible text for `ok`: 500 characters; timeout 15 s; 1 s between requests per domain
- Page contents are not stored; this table only.

| bank | class | status | text length | language | robots disallows home | method | final URL | title | notes |
|---|---|---|---|---|---|---|---|---|---|
| mkbank | ok | 200 | 13139 | uz_latn | no | httpx | https://mkbank.uz/uz/ | “Mikrokreditbank” ATB | no data |
| agrobank | ok | 200 | 4168 | uz_latn | no | browser | https://agrobank.uz/uz/person | Agrobank — O‘zbekistonda jismoniy shaxslar va biznes uchun bank xizmatlari | robots.txt 403 on agrobank.uz; httpx: js_shell (0 chars) |
| anor_bank | ok | 200 | 7572 | uz_latn | no | httpx | https://www.anorbank.uz/uz/ | ANORBANK — raqamli bank O‘zbekistonda, kreditlar va omonatlar \| ANORBANK UZ | no data |
| hayot_bank | js_shell | 200 | 0 | no data | no | browser | https://hayotbank.uz/main/individual/home | HAYOTBANK | httpx: js_shell (0 chars); browser error: Page.goto: Timeout 15000ms exceeded. |
| universal_bank | ok | 200 | 925 | uz_latn | no | httpx | https://universalbank.uz/ | Universalbank – Современный банк для физических и юридических лиц | no data |
| garant_bank | ok | 200 | 13522 | ru | no | httpx | https://garantbank.uz/ru | Garant bank | no data |

## Summary

| class | banks |
|---|---|
| ok | 5 |
| js_shell | 1 |
| blocked | 0 |
| unreachable | 0 |
| other | 0 |
| skipped (no website_url) | 15 |

Skipped: asakabank, turonbank, infinbank, trustbank, madad_invest_bank, saderat_bank, orient_finans_bank, ipoteka_bank, tenge_bank, ziraat_bank_uzbekistan, avo_bank, open_bank, tbc_bank, davr_bank, hamkorbank

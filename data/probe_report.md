# Bank website probe

- Run at: 2026-10-10 13:31 UTC
- User-Agent: `ComplianceRadar/0.1 (WIUT hackathon; consumer-protection research bot)`
- Min visible text for `ok`: 500 characters; httpx timeout 15 s; 1 s between requests per domain
- Browser fallback: on; network idle up to 45 s, one retry
- Page contents are not stored; this table only.

| bank | class | status | text length | language | robots disallows home | method | final URL | title | language versions | notes |
|---|---|---|---|---|---|---|---|---|---|---|
| mkbank | ok | 200 | 13139 | uz_latn | no | httpx | https://mkbank.uz/uz/ | “Mikrokreditbank” ATB | uz [link] /uz/ → 200 uz_latn (13139 chars); uz_cyrl [link] /oz/ → 200 uz_cyrl (12569 chars); ru [link] /ru/ → 200 ru (11914 chars) | no data |
| agrobank | ok | 200 | 4168 | uz_latn | no | browser | https://agrobank.uz/uz/person | Agrobank — O‘zbekistonda jismoniy shaxslar va biznes uchun bank xizmatlari | uz [link] /uz/about → 200 uz_latn (6685 chars); ru [guess] /ru/ → 200 ru (3135 chars) | robots.txt 403 on agrobank.uz; httpx: js_shell (0 chars) |
| anor_bank | ok | 200 | 7572 | uz_latn | no | httpx | https://www.anorbank.uz/uz/ | ANORBANK — raqamli bank O‘zbekistonda, kreditlar va omonatlar \| ANORBANK UZ | uz [link] /uz/about/ → 200 uz_latn (6688 chars); ru [link] / → 200 ru (6602 chars) | no data |
| hayot_bank | ok | 200 | 7558 | uz_latn | no | browser | https://hayotbank.uz/main/individual/home | Hayot Bank - jismoniy shaxslarga | uz [guess] /uz/ → 200 uz_latn (7558 chars); ru [guess] /ru/ → 200 uz_latn (7558 chars) | httpx: js_shell (0 chars) |
| universal_bank | ok | 200 | 925 | uz_latn | no | httpx | https://universalbank.uz/ | Universalbank – Современный банк для физических и юридических лиц | uz [guess] /uz/ → 200 uz_latn (925 chars); ru [guess] /ru/ → 200 ru (819 chars) | no data |
| garant_bank | ok | 200 | 13522 | ru | no | httpx | https://garantbank.uz/ru | Garant bank | uz [link] /uz → 200 uz_latn (14450 chars); ru [link] /ru/korporativnym-klientam → 200 ru (9637 chars) | no data |

## Summary

| class | banks |
|---|---|
| ok | 6 |
| js_shell | 0 |
| js_shell_failed | 0 |
| blocked | 0 |
| unreachable | 0 |
| other | 0 |
| skipped (no website_url) | 15 |

Skipped: asakabank, turonbank, infinbank, trustbank, madad_invest_bank, saderat_bank, orient_finans_bank, ipoteka_bank, tenge_bank, ziraat_bank_uzbekistan, avo_bank, open_bank, tbc_bank, davr_bank, hamkorbank

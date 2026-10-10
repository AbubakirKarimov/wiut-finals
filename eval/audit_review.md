## Auditor's reading of the Part 2 keyword hits

Keyword hits are leads. Reading each snippet (auditor's judgement, not system output):

| bank | requirement | strength | why |
|---|---|---|---|
| agrobank | main:18^1 | strong | "Kredit kalkulyator ... Avtokreditni hisoblash" on loan pages (not read by the batch crawl) |
| agrobank | main:40^4 | strong | "Omonatlaringiz kafolatlangan" on deposit pages (not read by the batch crawl) |
| anor_bank | main:28^1 | strong | document "kreditlarni restrukturizatsiya qilish (kredit shartnomalari shartlarini o‘zgartirish) tartibi" on /uz/about/documents/, a page the check DID read |
| mkbank | main:40^4 | strong | "Omonatlaringiz kafolatlangan." on /uz/private/deposit/ (not read by the batch crawl) |
| mkbank | main:18^1 | medium | menu item "Calculators" (English version); whether it calculates the full loan cost is unknown |
| garant_bank | main:40^4 | medium | "Участником Фонда гарантирования вкладов" and guarantee documents; the required visible link on the deposit page is not shown |
| mkbank | main:28^1 | weak (spurious) | "siyosatni qayta ko‘rib chiqish" in a quality policy; unrelated |

Possible false positives among the 17 possible_gap findings: **4 strong (24%)**, 6 with
strong or medium evidence (35%), 7 with any keyword hit (41%). Per requirement (strong /
gaps): 18^1 1/2, 28^1 1/5, 37^5 0/5, 40^4 2/5. These are not precision figures: only
analyst Confirm/Reject decisions measure precision.

## Part 5. Findings to verify manually (ranked by suspicion)

| # | bank | requirement | status | evidence URL | what to look for |
|---|---|---|---|---|---|
| 1 | anor_bank | main:28^1 | possible_gap | https://www.anorbank.uz/uz/about/documents/ | Is the document "Yuridik va jismoniy shaxslarga ajratilgan kreditlarni restrukturizatsiya qilish (kredit shartnomalari shartlarini o‘zgartirish) tartibi" listed and downloadable? If yes, the gap is wrong. |
| 2 | mkbank | main:40^4 | possible_gap | https://mkbank.uz/uz/private/deposit/ | Is "Omonatlaringiz kafolatlangan" a visible hyperlink on the deposit page, and where does it lead? |
| 3 | agrobank | main:40^4 | possible_gap | https://agrobank.uz/uz/person/deposits/baraka | Is "Omonatlaringiz kafolatlangan" shown as a clickable link on the deposit pages? |
| 4 | agrobank | main:18^1 | possible_gap | https://agrobank.uz/uz/person/loans/auto1 | Does the "Kredit kalkulyator" show the full cost of the loan (all interest and fees), or only the monthly payment? |
| 5 | mkbank | main:18^1 | possible_gap | https://mkbank.uz/uz/ | Open the "Kalkulyatorlar" menu item: is there a loan calculator for individuals that shows the full cost? |
| 6 | garant_bank | main:40^4 | possible_gap | https://garantbank.uz/ru/ | On a deposit page, is there a visible link "Ваши вклады гарантированы" / "Omonatlaringiz kafolatlangan" (not only a mention of the guarantee fund on "О банке")? |
| 7 | mkbank | main:51 | ok | https://mkbank.uz/uz/services/online-reception/send/ | On the homepage https://mkbank.uz/uz/ (not the cited page), are the call-centre numbers 1285 / +998 55 503-63-63 visible? |
| 8 | mkbank | main:49 | ok | https://mkbank.uz/uz/services/online-reception/send/ | On the homepage, is "Murojaat yuborish" a visible link in the header or top navigation (the cited quote is a breadcrumb on the complaint page)? |
| 9 | mkbank | main:17 | ok | https://mkbank.uz/oz/ | Does the "Банк ҳақида" link lead to information about the bank AND the terms of its services, as the clause requires? |
| 10 | garant_bank | main:7 | ok | https://garantbank.uz/uz | Only 2 of 11 Uzbek/Russian pages read were Uzbek: do the loan, deposit and tariff pages exist in Uzbek under /uz? |
| 11 | agrobank | main:28^1 | possible_gap | https://agrobank.uz/uz/person | Inconclusive (JavaScript-only site): look in the documents section for a loan restructuring / change-of-terms procedure. |
| 12 | agrobank | main:37^5 | possible_gap | https://agrobank.uz/uz/person | Inconclusive (JavaScript-only site): look for a procedure for releasing or replacing collateral (garov). |
| 13 | mkbank | main:37^5 | possible_gap | https://mkbank.uz/uz/corporate/ | The cited passage ("bosqichma-bosqich kuzating", a reporting feature) is unrelated: check the documents page for a collateral release procedure. |
| 14 | mkbank | main:14 | ok | https://mkbank.uz/uz/ | Does the "Sayt xaritasi" link (/uz/map/) open a page that shows the site structure? |
| 15 | hayot_bank | main:7 | ok | https://hayotbank.uz/main/individual/home | Is there a working Russian/Uzbek language switch, given that /ru/ returned Uzbek text in the probe? |

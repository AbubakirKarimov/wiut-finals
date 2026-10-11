# Requirement candidates for review

Generated 2026-10-10T14:05:58.055785+00:00 by `python -m backend.requirements.shortlist` (openai-compatible:api.groq.com, model openai/gpt-oss-120b).
All candidates have approved=false. Approve after reading with:
`python -m backend.requirements.approve <clause_id> ...`

| Step | Count |
|---|---|
| eligible clauses | 175 |
| passed pre-filter | 80 |
| sent to LLM | 80 |
| LLM errors (invalid JSON after retry) | 0 |
| judged checkable by LLM | 36 |
| shortlisted (checkable + always-include) | 36 |
| run: llm_api_calls | 163 |
| run: llm_failed_calls | 83 |
| run: llm_cache_hits | 0 |
| run: input_tokens | 72428 |
| run: output_tokens | 42308 |
| run: api_time_s | 163.6 |
| run: cost_usd | 0.036249 |

## Shortlist (36)

### cbu_reg_3030:main:40^4
- lex.uz: https://lex.uz/ru/docs/3804290#7816849
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.98
- Pre-filter topics: disclosure, website
- Requirement (English, machine translation): The bank must place a visible hyperlink with the text “Your deposits are guaranteed” on its deposit information page that links to the corresponding page on the Deposit Guarantee Agency’s official website.
- Evidence to look for: On the bank’s deposit products or deposits information page, locate a hyperlink labeled “Your deposits are guaranteed” and verify that its URL points to the Deposit Guarantee Agency’s official website.

Original text (Uzbek Cyrillic):

> 40^4. Банкнинг расмий веб-сайтида омонатлар тўғрисидаги ахборот жойлаштирилган саҳифада «Омонатларингиз кафолатланган» деган мазмунда кўзга ташланадиган тегишли ҳавола (гиперҳавола) жойлаштириши ва ушбу тегишли ҳавола (гиперҳавола) Омонатларни кафолатлаш агентлигининг расмий веб-сайтидаги тегишли саҳифага йўналтирилиши керак.

### cbu_reg_3030:main:13
- lex.uz: https://lex.uz/ru/docs/3804290#3804958
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.97
- Pre-filter topics: disclosure, website (always included)
- Requirement (English, machine translation): The bank must have an official website and must display the date of the information posted on it.
- Evidence to look for: Look for a visible date (e.g., “Updated on …”) on the bank’s public pages such as the homepage or product pages.

Original text (Uzbek Cyrillic):

> 13. Банк ўзининг расмий веб-сайтига эга бўлиши шарт.
> Расмий веб-сайтга жойлаштирилаётган ахборотларнинг санаси кўрсатилиши керак.

### cbu_reg_3030:main:14
- lex.uz: https://lex.uz/ru/docs/3804290#3804959
- Proposed check_type: required_document
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.97
- Pre-filter topics: website (always included)
- Requirement (English, machine translation): The bank must provide a section on its official website that describes the site structure and allows easy identification of the location of each page.
- Evidence to look for: A site map or 'Website Structure' page/section listing all pages and their locations, typically linked in the footer or navigation.

Original text (Uzbek Cyrillic):

> 14. Банкнинг расмий веб-сайтида сайтнинг тузилишини баён этувчи, ушбу тузилмадаги расмий веб-сайтнинг ҳар бир саҳифаси жойлашган жойни қулай шаклда аниқлаш имконини берувчи бўлим бўлиши керак.

### cbu_reg_3030:main:17
- lex.uz: https://lex.uz/ru/docs/3804290#3804968
- Proposed check_type: required_document
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.97
- Pre-filter topics: website (always included)
- Requirement (English, machine translation): The bank must provide a link on its homepage that leads to a section containing information about the bank and the terms of the services offered.
- Evidence to look for: A hyperlink on the homepage pointing to a page or section (e.g., “About the bank”, “Service terms”) that presents information about the bank and its service conditions.

Original text (Uzbek Cyrillic):

> 17. Банк расмий веб-сайтининг мазкур банк ва кўрсатилаётган банк хизматлари шартлари тўғрисида ахборотларни ўз ичига олган бўлимига веб-сайтнинг бош саҳифасидан гиперҳаволалар орқали бир ўтишда кириш учун имкони яратилган бўлиши керак.

### cbu_reg_3030:main:23
- lex.uz: https://lex.uz/ru/docs/3804290#3804980
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.97
- Pre-filter topics: complaints, disclosure, tariffs_fees, website
- Requirement (English, machine translation): The bank must publish on its official website its full and short name, address, branch addresses, working hours, contact phone numbers, website and email, the text of this regulation, the procedures, terms and fees for services (including sample contract texts), tariffs, interest rates and commissions, foreign exchange rates, the procedure for handling consumer complaints and the methods for protecting consumer rights, including court dispute resolution.
- Evidence to look for: Look for pages such as About, Contact, Regulations, Tariffs, Consumer Rights, Sample Contracts that contain the listed information.

Original text (Uzbek Cyrillic):

> 23. Банкнинг ахборот стендларида ва расмий веб-сайтида қуйидаги ахборотлар жойлаштирилиши шарт:
> банкнинг тўлиқ ва қисқартирилган номи, манзили, филиаллари манзиллари, иш вақти, боғланиш учун алоқа телефонлари, расмий веб-сайти ва электрон почта манзили;
> мазкур Низомнинг матни;
> истеъмолчиларга банк хизматларини кўрсатиш тартиби, шартлари ва қиймати, шу жумладан банк хизмати бўйича намунавий шартномалар матни (фақат расмий веб-сайтда);
> банк операциялари бўйича тарифлар, фоиз ставкалари ва воситачилик ҳақлари тўғрисида;
> чет эл валюталарини сотиш ва сотиб олиш курслари, чет эл валюталарини алмаштириш курслари, шунингдек валюта айирбошлаш операциялари учун ундириладиган воситачилик ҳақи миқдорлари (агарда мавжуд бўлса);
> истеъмолчилар мурожаатларини кўриб чиқиш тартиби, шу жумладан мурожаат қилиш усуллари ва улар йўлланадиган манзиллар тўғрисида;
> истеъмолчининг ҳуқуқларини ҳимоя қилиш усуллари, шу жумладан низони судгача ҳал этиш имконияти ва усуллари ҳақида.

### cbu_reg_3030:main:28^1
- lex.uz: https://lex.uz/ru/docs/3804290#7816721
- Proposed check_type: required_document
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.97
- Pre-filter topics: disclosure, tariffs_fees, website
- Requirement (English, machine translation): The bank must publish on its official website the procedure for reviewing consumer applications to modify or add to loan contract terms (restructuring), including all items listed in the clause.
- Evidence to look for: A dedicated page or downloadable PDF (e.g., titled “Loan Restructuring Procedure” or similar) that contains the detailed list of types of restructuring, qualifying circumstances, application acceptance and registration rules, required documents, review timelines, evaluation criteria, notification procedures, and special rules for pregnant or postpartum women.

Original text (Uzbek Cyrillic):

> 28^1. Банклар молиявий қийинчиликлар, мураккаб ҳаётий вазиятларга тушиб қолган ҳамда форс-мажор ҳолатлари туфайли ўз вақтида кредит тўловларини амалга оширишга қийналаётган истеъмолчиларнинг амалдаги кредитлари бўйича кредит шартномаси шартларига ўзгартириш ва қўшимчалар киритиш (реструктуризация) имкониятлари борасидаги аризаларини кўриб чиқиш тартибига эга бўлиши ва ушбу тартибни банкнинг расмий веб-сайтида жойлаштириши шарт.
> Мазкур тартиб камида қуйидагиларни ўз ичига қамраб олиши лозим:
> кредит шартномаси шартларига ўзгартириш ва қўшимчалар киритишнинг (реструктуризация) турлари (масалан, кредит тўловлари муддатини узайтириш, кредит фоиз ставкасини қайта кўриб чиқиш, кредит тўловларини кечиктирганлик учун жарима ва пенялар миқдорини камайтириш ва бошқалар);
> кредит шартномаси шартларига ўзгартириш ва қўшимчалар киритишга (реструктуризацияга) асос бўладиган молиявий қийинчиликлар, мураккаб ҳаётий вазиятлар ҳамда форс-мажор ҳолатлар рўйхати;
> истеъмолчининг аризаларини қабул қилиш, рўйхатга олиш тартиби ҳамда аризага илова қилинадиган зарур ҳужжатларнинг рўйхати;
> истеъмолчининг аризаларини кўриб чиқиш муддатлари;
> қабул қилинган аризаларни кўриб чиқиш ва баҳолаш мезонлари;
> ариза бўйича банк томонидан қабул қилинган қарор ҳақида истеъмолчига хабар бериш тартиби ва муддати;
> ариза қаноатлантирилган тақдирда, кредит шартномаси ҳамда унинг иловаларига қўшимча ва ўзгартиришлар киритиш тартиби;
> аризани қанотлантиришни рад этиш бўйича қарор қабул қилинганда, бу тўғрисида асослантирилган ҳолда аризачига хабар бериш тартиби.
> Бунда ушбу тартибда ҳомиладорлик ва туғиш таътилини олган аёлларнинг амалдаги кредитлари бўйича тўловлар муддатини ўн ойгача узайтириш тўғрисидаги аризаларини кўриб чиқиш бўйича қоидалар мажбурий тарзда акс эттирилиши лозим.

### cbu_reg_3030:main:49
- lex.uz: https://lex.uz/ru/docs/3804290#7170589
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.97
- Pre-filter topics: complaints, disclosure, website
- Requirement (English, machine translation): The bank must provide a clearly visible link on its homepage or top navigation that leads directly to a page where consumer complaints can be submitted.
- Evidence to look for: Look for a prominently placed link on the homepage or in the fixed top menu (e.g., labeled “Complaints”, “Consumer complaints”, or similar) that opens a dedicated page with a complaint submission form or contact details.

Original text (Uzbek Cyrillic):

> 49. Банк истеъмолчиларнинг мурожаатларини кўриб чиқиши ва кўриб чиқиш натижалари бўйича мурожаат этувчиларга жавоб бериши лозим.
> Банк оғзаки, ёзма ёхуд электрон шаклдаги мурожаатларни қабул қилиш учун шароитлар яратиши зарур.
> Банк истеъмолчиларга хизмат кўрсатиш офисларида (ёки марказларида), филиалларида ва ўзининг расмий веб-сайти орқали мурожаатларни қабул қилишни йўлга қўяди. Банк расмий веб-сайтининг бош саҳифасида ёки сайтнинг ўзгармас юқори қисмида (ушбу саҳифада) яққол кўринарли тарзда жойлаштирилган ҳавола орқали тўғридан-тўғри ўтиш мумкин бўлган бошқа саҳифасида мурожаатларни қабул қилишни ташкил этади.
> Банк мобил иловасида истеъмолчилар томонидан мурожаат қолдирилиши учун имконият яратади ва/ёки мурожаат юборилиши учун алоқа каналларини кўрсатиши керак.
> Банк истеъмолчилар билан телефон алоқаси орқали боғланишини таъминловчи Call-марказларни ташкил этиб, у орқали истеъмолчиларга банк фаолияти билан боғлиқ маслаҳатлар ва тушунтиришлар беради ҳамда оғзаки шаклдаги мурожаатларни қабул қилади.

### cbu_reg_3030:main:51
- lex.uz: https://lex.uz/ru/docs/3804290#7170595
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.97
- Pre-filter topics: disclosure, website
- Requirement (English, machine translation): The bank must display the call‑center telephone numbers on the homepage of its official website in a location visible to consumers.
- Evidence to look for: Bank's homepage showing the call‑center phone numbers (e.g., in header, footer or a dedicated contact section).

Original text (Uzbek Cyrillic):

> 51. Call-марказ телефонларининг рақамлари банк расмий веб-сайтининг бош саҳифасида, шунингдек, банк ва унинг филиалларидаги ахборот стендларида ҳамда банк (филиал) биносидан ташқарида ташкил этилган банк хизматлари марказлари ва кассаларнинг истеъмолчига кўринарли жойда ўқишга имконияти бўлган ҳолда жойлаштирилиши керак.

### cbu_reg_3030:main:7
- lex.uz: https://lex.uz/ru/docs/3804290#5289561
- Proposed check_type: uz_version
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.97
- Pre-filter topics: state_language
- Requirement (English, machine translation): The bank must provide information about its financial services to consumers in Uzbek, using clear and plain language.
- Evidence to look for: Uzbek-language versions of main service pages (loans, deposits, tariffs, terms) and a language selector showing Uzbek.

Original text (Uzbek Cyrillic):

> 7. Банк ўзининг молиявий хизматлари тўғрисидаги маълумотларни истеъмолчиларга давлат тилида етказиши лозим. Банкнинг молиявий хизматлари тўғрисидаги маълумотлар қўшимча равишда бошқа тилларда ҳам тақдим этилиши мумкин.
> Банк хизматлари тўғрисидаги маълумотларнинг матни лўнда, оддий ва равон тилда баён этилиши керак.

### law_state_language:art:20
- lex.uz: https://lex.uz/ru/docs/121051#121250
- Proposed check_type: uz_version
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.97
- Pre-filter topics: publication, state_language (always included)
- Requirement (English, machine translation): The bank must publish all informational materials such as forms, announcements, price lists and other public information in the state language (Uzbek) on its website.
- Evidence to look for: Uzbek-language versions of key public pages (e.g., loans, deposits, tariffs, terms) and a language selector showing Uzbek are present on the site.

Original text (Uzbek Cyrillic):

> 20-модда.
> Лавҳалар, эълонлар, нархномалар ва бошқа кўргазмали ҳамда оғзаки ахборот матнлари давлат тилида расмийлаштирилади ва эълон қилинади ҳамда бошқа тилларда таржимаси берилиши мумкин.

### cbu_reg_3030:main:16
- lex.uz: https://lex.uz/ru/docs/3804290#3804961
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.96
- Pre-filter topics: disclosure, tariffs_fees, website
- Requirement (English, machine translation): Consumers must be able to access required information on the bank’s public website at any time, free of charge, without registration, without providing personal data, and without any encryption or other protection.
- Evidence to look for: Open a typical public page (e.g., loans, deposits, tariffs) and verify that the information is displayed without any login prompt, fee notice, or request for personal data.

Original text (Uzbek Cyrillic):

> 16. Банкнинг расмий веб-сайтидаги ахборотдан фойдаланишда:
> истеъмолчилар зарур маълумотлардан хоҳлаган пайтида танишиб чиқиш ва ундан фойдаланиш имконига эга бўлиши керак. Маълумот билан танишганлик ёки ундан бошқача тарзда фойдаланганлик учун ҳақ ундирилмаслиги ҳамда бошқа чекловлар қўйилмаслиги лозим;
> истеъмолчи маълумот билан бепул ва кенг тарқалган дастурий таъминот ёрдамида фойдаланиш имконига эга бўлиши лозим;
> ахборот шифрланган ёки бошқа воситалар орқали ҳимояланган бўлмаслиги керак;
> банк ўз расмий веб-сайтида жойлаштирилган ахборотдан (истеъмолчининг шахсий кабинетида жойлаштирилган ахборотдан ташқари) фойдаланиш учун истеъмолчидан рўйхатдан ўтиш ёки шахсий маълумотларини тақдим этишини, шунингдек у билан турли хил битимлар тузишни талаб қилишга ҳақли эмас.

### cbu_reg_3030:main:37^5
- lex.uz: https://lex.uz/ru/docs/3804290#7643494
- Proposed check_type: required_document
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.96
- Pre-filter topics: collateral, disclosure, website
- Requirement (English, machine translation): The bank must publish on its official website a separate procedure describing the step‑by‑step release or substitution of pledged assets for secured loans.
- Evidence to look for: A dedicated page or downloadable document on the bank's website outlining the procedure for stepwise release or substitution of pledged assets, including application registration, decision timelines and notification requirements.

Original text (Uzbek Cyrillic):

> 37^5. Банклар ажратилган кредит таъминотига қабул қилинган гаров мулкларини кредитнинг асосий қарзи қолдиғига мутаносиб равишда босқичма-босқич гаровдан чиқариш ёки гаров нарсасини алмаштириш бўйича қуйидагиларни ўз ичига олувчи алоҳида тартибга эга бўлиши ва ушбу тартиб банкнинг расмий веб-сайтида жойлаштирилиши лозим:
> қарз олувчи ёки гаровга қўювчининг гаровга қўйилган мол-мулкларни босқичма-босқич гаровдан чиқариш ёки гаров нарсасини алмаштириш бўйича аризасини рўйхатга олиш ҳамда ушбу аризани кўриб чиқиш муддати;
> гаровга қўйилган мол-мулкларни босқичма-босқич гаровдан чиқариш ёки гаров нарсасини алмаштириш масаласини кўриб чиқиш ва тегишли қарорни қабул қилиш бўйича банкнинг ваколатли органи тўғрисида ҳамда мазкур ваколатли органнинг қарори ҳақида аризачига хабар бериш муддати;
> гаровга қўйилган мол-мулкларни босқичма-босқич гаровдан чиқариш ёки гаров нарсасини алмаштиришни рад этиш бўйича қарор қабул қилинганда, бу тўғрисида асослантирилган ҳолда аризачига хабар бериш.
> Банк кредит бўйича тузиладиган гаров шартномасида банкнинг гаров таъминотига қўйилган талаблардан келиб чиққан ҳолда қарз олувчининг кредитнинг қопланмаган қисмидан ортиқ суммада гаров таъминоти суммасини камайтириш ҳуқуқини, шунингдек гаров таъминотини камайтириш тартиби ва усулларини акс эттириши шарт.
> Кредит қарздорлигини қоплаш мақсадида банк гаровга қўйилган мол-мулкни суддан ташқари тартибда қонунчиликда тақиқланмаган усуллар орқали гаровга қўювчи билан қонунчиликда белгиланган тартибда келишган ҳолда реализация қилиши мумкин.
> Бунда, банк мол-мулкни реализация қилишдан тушган маблағларни кредит қарздорлиги ва бошқа харажатларга йўналтирилиши юзасидан қарз олувчи ва гаровга қўювчига ёзма маълумот юборилишини таъминлаши лозим.

### law_state_language:art:17
- lex.uz: https://lex.uz/ru/docs/121051#121236
- Proposed check_type: uz_version
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.96
- Pre-filter topics: state_language
- Requirement (English, machine translation): The bank must provide its publishing activity in the state language (Uzbek) and, as needed, also in other languages.
- Evidence to look for: Verify that key public pages such as loans, deposits, tariffs, and terms are available in Uzbek and that language selection links include Uzbek.

Original text (Uzbek Cyrillic):

> 17-модда.
> Ноширлик фаолияти давлат тилида, эҳтиёжларни ҳисобга олган ҳолда эса, бошқа тилларда ҳам амалга оширилади.

### cbu_reg_3030:main:30^1
- lex.uz: https://lex.uz/ru/docs/3804290#7643405
- Proposed check_type: required_document
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.93
- Pre-filter topics: complaints, terms_offer, website
- Requirement (English, machine translation): The bank must provide on its public website an interactive, free information sheet for credit, credit card and term deposit products that consumers can fill out and download.
- Evidence to look for: A dedicated page or link on the bank’s website offering an interactive ‘Information Sheet’ for credit, credit card and term deposit products, with a fill‑in form and a download option (e.g., PDF or web form).

Original text (Uzbek Cyrillic):

> 30^1. Истеъмолчи-жисмоний шахс кредит, шу жумладан кредит картасини олиш ёки омонат ҳисобварағи очиш учун банкка мурожаат қилганида (банк биносига истеъмолчи ташриф буюрганда) банк мазкур Низомнинг 2-иловасига мувофиқ кредитнинг, 3-иловасига мувофиқ муддатли омонатнинг ҳамда 3а-иловасига мувофиқ кредит картанинг асосий шартлари тўғрисидаги ахборот варақасини (бундан буён матнда Ахборот варақаси деб юритилади) истеъмолчи — жисмоний шахс билан биргаликда тўлдиради ва истеъмолчи — жисмоний шахсга тақдим этади.
> Бунда мобил илова орқали кредит, шу жумладан кредит картасини олишда ҳамда муддатли омонат очишда, банк томонидан истеъмолчига ахборот варақаси билан танишиб чиқиш ва уни юклаб олиш имконияти яратилиши лозим.
> Банк ўзининг расмий веб-сайтида истеъмолчиларга тақдим этилаётган омонат, кредит, шу жумладан кредит карта маҳсулотлари бўйича Ахборот варақасининг интерактив шаклини мустақил равишда тўлдириш ва ундан нусха олиш имкониятини яратиб бериши лозим.
> Ахборот варақаси истеъмолчи — жисмоний шахсга бепул тарзда тақдим этилади ҳамда кредит, шу жумладан кредит картасини олиш ёки омонат ҳисобварағи очиш учун буюртманома ҳисобланмайди.

### cbu_reg_3030:main:58^17
- lex.uz: https://lex.uz/ru/docs/3804290#8383906
- Proposed check_type: required_document
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.93
- Pre-filter topics: complaints, publication, website
- Requirement (English, machine translation): The bank must publish quarterly and annual information notes (comments) on the aggregation and analysis of consumer complaints on its official website by the deadlines specified in the regulation.
- Evidence to look for: Look for publicly accessible web pages or downloadable PDF files on the bank’s website that contain quarterly complaint analysis reports (published by the 20th of the month following the quarter) and an annual complaint analysis report (published by February 15).

Original text (Uzbek Cyrillic):

> 58^17. Банк ҳар чорак (йил) натижаларига кўра мурожаатларни умумлаштиради ва таҳлил қилади.
> Мурожаатларни умумлаштириш ва таҳлил қилиш натижаларига кўра маълумотномалар (шарҳлар) тузилади, уларда мурожаатлар билан ишлашнинг умумий кўрсаткичлари, мурожаатларнинг турлари, сони ва келиб чиқиш сабаблари, мурожаатларда тез-тез кўтарилган масалалар, мурожаатлар банк хизмат турлари (маҳсулотлари) бўйича қайси ҳудудлардан келиб тушиши, ушбу банк хизматлари истеъмолчилар талабларидан келиб чиқиб уларга мос ишлаб чиқилганлиги ва истеъмолчилар билан адолатли муносабат қурилганлиги тўғрисида таҳлилий маълумотлар, мурожаатларни кўриб чиқиш якунлари бўйича аниқланган асосий камчиликлар ва қоидабузарликлар, истеъмолчиларнинг ҳуқуқлари ва қонуний манфаатлари бузилишини келтириб чиқарувчи сабабларни бартараф этиш мақсадида кўрилган чора-тадбирлар акс эттирилади.
> Банк бошқаруви банк фаолиятининг чорак (йил) натижаларини кўриб чиқиш тўғрисидаги ўз йиғилишларида банкда мурожаатлар билан ишлаш ҳолатини, шу жумладан мурожаатларни умумлаштириш ва таҳлил қилиш натижалари бўйича маълумотномаларни (шарҳларни), мурожаатларда кўтарилган салбий ҳолатларни, тизимли камчиликларни ва ўзига хос таваккалчиликларни муҳокама қилиши ҳамда истеъмолчиларнинг ҳуқуқлари бузилишига олиб келувчи тизимли камчиликларни бартараф этиш бўйича мазкур Низомнинг 5-иловасига мувофиқ ҳаракатлар режаларини тасдиқлаши лозим.
> Бунда, банк бошқаруви қарорлари, шунингдек, мурожаатларни умумлаштириш ва таҳлил қилиш натижалари бўйича маълумотномалар (шарҳлар) ички аудит хизматига тақдим этилади. Ички аудит хизмати банкда мурожаатлар билан ишлаш ҳолатини текшириш ўтказиш бўйича иш режаларини тузишда ва мониторинг фаолиятини амалга оширишда фойдаланади.
> Қуйидаги ҳолатлардан бирининг мавжудлиги тизимли камчиликларни бартараф этиш чоралари кўрилмаган деб ҳисобланишига асос бўлади:
> тизимли камчиликларни бартараф этиш бўйича ҳаракатлар режаларининг тасдиқланмаслиги;
> ҳаракатлар режаларида белгиланган чоралар ва топшириқларнинг ўз муддатларида бажарилмаслиги;
> белгиланган чоралар бажарилганига қарамасдан тизимли камчиликларнинг сақланиб қолиши;
> ички аудит хизмати томонидан ҳаракатлар режаларида қайд этилган топшириқлар ижроси ушбу топшириқларни бажариш муддати якунига қадар баҳоланмаганлиги, ҳар чорак натижалари бўйича чорак якунлангандан сўнг бир ой муддат давомида банк бошқаруви ва кузатув кенгашига ҳаракатлар режаларида қайд этилган топшириқларнинг бажарилиши ҳолати, шу жумладан қисман ёки тўлиқ бажарилмаган топшириқлар юзасидан хулоса киритилмаслиги ҳамда ҳар йил якуни бўйича бир ой давомида аҳоли ва юридик шахслар мурожаатларини кўриб чиқиш тизими самарадорлиги баҳоланмаганлиги;
> банк бошқаруви ички аудит хизмати томонидан тақдим этилган хулосаларда қайд этилган ҳолатларни хулоса тайёрланган санадан бошлаб бир ой давомида кўриб чиқмаганлиги.
> Мурожаатларни умумлаштириш ва таҳлил қилиш натижаларига кўра тузилган чораклик маълумотномалар (шарҳлар) ҳисобот чорагидан кейинги ойнинг 20-санасига ва йиллик маълумотномалар (шарҳлар) февраль ойининг 15-санасига қадар банкнинг расмий веб-сайтларида эълон қилиниши шарт.
> Банк акциядорларининг йиллик умумий йиғилишида тасдиқланадиган йиллик ҳисоботда банкнинг мурожаатлар билан ишлаш фаолияти тўғрисидаги маълумотлар ҳам акс эттирилади.
> Банк мазкур бандда назарда тутилган мурожаатлар масаласига оид Банк бошқаруви йиғилиши қарори (ҳужжат) нусхаларини у тасдиқланган кундан бошлаб уч иш куни ичида, шунингдек, ҳаракатлар режасидаги ҳар бир тизимли камчилик бартараф этилганлиги тўғрисидаги маълумотларни камчиликлар бартараф этилган кундан бошлаб беш иш куни ичида Марказий банкка тақдим этади.

### cbu_reg_3030:main:18^1
- lex.uz: https://lex.uz/ru/docs/3804290#7643197
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.92
- Pre-filter topics: credit_cost, website (always included)
- Requirement (English, machine translation): Banks must provide on their public website a tool that allows natural persons to independently calculate the full cost of loans intended for individuals.
- Evidence to look for: A loan cost calculator page or widget on the bank’s website, such as a page titled “Loan calculator”, “Credit cost calculator”, or similar, where users can input parameters and obtain the total loan cost.

Original text (Uzbek Cyrillic):

> 18^1. Банклар ўзларининг расмий веб-сайтларида, шунингдек мобил иловаларида (агар мавжуд бўлса) жисмоний шахсларга мўлжалланган кредитларнинг тўлиқ қийматини мустақил ҳисоблаб чиқиш имкониятини яратиб беришлари лозим.

### law_state_language:art:3
- lex.uz: https://lex.uz/ru/docs/121051#121106
- Proposed check_type: uz_version
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.88
- Pre-filter topics: state_language
- Requirement (English, machine translation): The bank must provide its key public pages (e.g., loans, deposits, tariffs, terms) in Uzbek, the state language.
- Evidence to look for: Uzbek-language versions of the main product pages or a language selector showing Uzbek on the website.

Original text (Uzbek Cyrillic):

> 3-модда.
> Ўзбек тилининг Ўзбекистон Республикаси ҳудудида давлат тили сифатида амал қилишининг ҳуқуқий асослари ушбу Қонун ва бошқа қонун ҳужжатлари билан белгилаб берилади.
> Тилнинг Қорақалпоғистон Республикасида амал қилишига боғлиқ масалалар, шунингдек Қорақалпоғистон Республикасининг қонунчилиги билан белгиланади.
> Ўзбекистон Республикасининг Конституциявий Қонуни билан махсус ҳуқуқий режим ўрнатилган ҳудудда ушбу Қонунда белгиланганидан бошқача иш юритиш ва расмий ҳужжатларни қабул қилиш тили белгиланиши мумкин.
> Ушбу Қонун тилларнинг турмушда, шахслараро муомалада ҳамда диний ва ибодат билан боғлиқ удумларни адо этишда қўлланишини тартибга солмайди.
> Фуқаролар миллатлараро муомала тилини ўз хоҳишларига кўра танлаш ҳуқуқига эгадирлар.

### cbu_reg_3030:main:5
- lex.uz: https://lex.uz/ru/docs/3804290#4427417
- Proposed check_type: required_document
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.86
- Pre-filter topics: disclosure, publication, website
- Requirement (English, machine translation): The bank must publish its service provision terms and any changes to them, as well as currency exchange rate changes, on its official public website.
- Evidence to look for: A 'Terms of Service' or similar page (or PDF) on the website showing current terms and a change log, and a section announcing currency exchange rate updates.

Original text (Uzbek Cyrillic):

> 5. Банк хизматларини тақдим этиш шартлари, ушбу шартларнинг ўзгариши ҳақидаги маълумотлар банкнинг расмий веб-сайтида эълон қилиниши, шунингдек банкнинг ахборот стендларида доимий равишда жойлаштириб борилиши керак.
> Бунда, банк хизматларини тақдим этиш шартларининг ўзгариши ҳақидаги маълумот кучга киришидан камида ўн кун олдин, валюта айирбошлаш курсларининг ўзгариши тўғрисидаги маълумот зудлик билан эълон қилиниши лозим.

### cbu_reg_3030:main:58^4
- lex.uz: https://lex.uz/ru/docs/3804290#7170627
- Proposed check_type: required_document
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.86
- Pre-filter topics: disclosure, website
- Requirement (English, machine translation): The bank must publish on its official website a schedule for personal acceptance of consumers, including representatives of individuals and legal entities, in accordance with the posted timetable.
- Evidence to look for: A page or downloadable document (e.g., PDF) on the bank’s website titled “Acceptance schedule”, “Consumer reception timetable” or similar, showing dates and times for personal acceptance of physical and legal persons.

Original text (Uzbek Cyrillic):

> 58^4. Банкнинг мансабдор шахслари банкнинг расмий веб-сайти ва ахборот стендларида жойлаштирилган жисмоний шахсларни ва юридик шахсларнинг вакилларини қабул қилиш жадвалига мувофиқ истеъмолчиларни шахсан қабул қилишлари шарт. Шахсий қабул баённома асосида расмийлаштирилади ёки истеъмолчини хабардор қилган ҳолда махсус (аудио ва видео) техника воситалари ёрдамида овозлар ёзиб олиниши ёки видеотасвирга туширилиши мумкин.

### law_state_language:art:24
- lex.uz: https://lex.uz/ru/docs/121051#121264
- Proposed check_type: uz_version
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.86
- Pre-filter topics: state_language
- Requirement (English, machine translation): The bank must not discriminate against the state language or other languages and must allow citizens to freely choose the language of communication, education, and upbringing.
- Evidence to look for: Uzbek-language versions of key public pages (loans, deposits, tariffs, terms) and language selection links on the website.

Original text (Uzbek Cyrillic):

> 24-модда.
> Ўзбекистон Республикасида давлат тилига ёки бошқа тилларга менсимай ёки хусумат билан қараш тақиқланади. Фуқароларнинг ўзаро муомала, тарбия ва таълим олиш тилини эркин танлаш ҳуқуқини амалга оширишга тўсқинлик қилувчи шахслар қонунчиликка мувофиқ жавобгар бўладилар.

### cbu_reg_3030:annex1:7
- lex.uz: https://lex.uz/ru/docs/3804290#7643550
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.85
- Pre-filter topics: tariffs_fees
- Requirement (English, machine translation): If a loan’s interest rate is linked to base indicators, the bank must use the current day’s base indicator values when calculating the loan interest rate.
- Evidence to look for: Loan product or terms page stating that the interest rate is linked to the Central Bank’s key rate and inflation and that the calculation uses the indicators of the calculation day.

Original text (Uzbek Cyrillic):

> 7. Агар кредитнинг фоиз ставкаси базавий кўрсаткичларга (Марказий банкнинг асосий ставкаси, инфляция даражаси ва бошқалар) боғланган бўлса, у ҳолда банк КТҚни ҳисоблашда шу кундаги базавий кўрсаткичларнинг миқдоридан фойдаланади.

### cbu_reg_3030:main:4
- lex.uz: https://lex.uz/ru/docs/3804290#3804933
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.85
- Pre-filter topics: disclosure
- Requirement (English, machine translation): The bank must disclose information about all its services to consumers, ensuring that such information does not contain commercial or bank secrets.
- Evidence to look for: A public page (e.g., Products, Services, or Tariffs) that lists and describes all banking services offered.

Original text (Uzbek Cyrillic):

> 4. Банк томонидан кўрсатиладиган барча хизматлар тўғрисида маълумотлар истеъмолчига ошкор этилиши лозим.
> Хизматлар тўғрисидаги маълумотлар тижорат ёки банк сирини ўз ичига олмаслиги зарур.

### cbu_reg_3030:main:40^3
- lex.uz: https://lex.uz/ru/docs/3804290#7816845
- Proposed check_type: required_document
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.85
- Pre-filter topics: disclosure, website
- Requirement (English, machine translation): The bank must publish information about the deposit guarantee system on its official website.
- Evidence to look for: A dedicated page or downloadable document on the bank’s public website (e.g., titled “Deposit guarantee system” or similar) containing the required information.

Original text (Uzbek Cyrillic):

> 40^3. Мазкур Низомнинг 40^2-бандида назарда тутилган ахборотлар банк томонидан қуйидаги шаклларда тарқатилиши шарт:
> банкнинг ахборот стендлари ва расмий веб-сайтида жойлаштириш орқали;
> администраторлар орқали, шу жумладан банк омонати (депозити) шартномаси ва (ёки) банк ҳисобварағи шартномасини тузиш жараёнида ҳамда истеъмолчининг сўровига асосан;
> масофавий хизмат кўрсатиш тизимлари орқали.

### law_state_language:art:14
- lex.uz: https://lex.uz/ru/docs/121051#121154
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.85
- Pre-filter topics: complaints, state_language
- Requirement (English, machine translation): The bank must allow persons to submit applications, proposals and complaints in Uzbek and other languages.
- Evidence to look for: A contact or complaints page stating that submissions are accepted in Uzbek (the state language) and other languages.

Original text (Uzbek Cyrillic):

> 14-модда.
> Ўзбекистон Республикаси ҳудудида яшовчи шахсларга давлат ташкилотлари ва муассасаларига, жамоат бирлашмаларига аризалар, таклифлар, шикоятлар билан давлат тилида ва бошқа тилларда мурожаат қилиш ҳуқуқи таъминланади.

### law_state_language:art:22
- lex.uz: https://lex.uz/ru/docs/121051#1883413
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.85
- Pre-filter topics: state_language
- Requirement (English, machine translation): Geographic object names must be presented in the state language (Uzbek).
- Evidence to look for: Check the branch locations or service area page and verify that city, region and other geographic names are written in Uzbek.

Original text (Uzbek Cyrillic):

> 22-модда.
> Географик объектларнинг номлари давлат тилида акс эттирилади.

### law_state_language:art:7
- lex.uz: https://lex.uz/ru/docs/121051#121120
- Proposed check_type: uz_version
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.85
- Pre-filter topics: state_language
- Requirement (English, machine translation): The bank must use the Uzbek literary language, following its scientific rules and norms, in all official public materials.
- Evidence to look for: Uzbek-language versions of key public pages such as loans, deposits, tariffs, and terms are available on the website, indicated by language selectors or Uzbek text on those pages.

Original text (Uzbek Cyrillic):

> 7-модда.
> Давлат тили расмий амал қиладиган доираларда ўзбек адабий тилининг амалдаги илмий қоидалари ва нормаларига риоя этилади.
> Давлат ўзбек тилининг бойитилиши ва такомиллаштирилишини таъминлайди, шу жумладан унга ҳамма эътироф қилган илмий-техникавий ва ижтимоий-сиёсий атамаларни жорий этиш ҳисобига таъминлайди.
> Янги илмий асосланган атамалар жамоатчилик муҳокамасидан кейин ва Олий Мажлис палаталари тегишли қўмиталарининг розилиги билан ўзбек тилига жорий этилади.

### cbu_reg_3030:annex1:2
- lex.uz: https://lex.uz/ru/docs/3804290#5789547
- Proposed check_type: required_document
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.78
- Pre-filter topics: collateral, credit_cost
- Requirement (English, machine translation): When calculating the effective interest rate, the bank must include all payments listed in the clause, such as principal and interest, payments to the bank’s profit, payments to third parties, insurance-related payments, collateral insurance, guarantee fees, and intermediary service fees.
- Evidence to look for: Locate a publicly posted document or web page (e.g., a PDF titled “Methodology for calculating the effective interest rate (KТҚ)” or a similar section on the bank’s website) that enumerates the payment types to be included in the KТҚ calculation as specified in the clause.

Original text (Uzbek Cyrillic):

> 2. КТҚни ҳисоблаб чиқишда қарз олувчининг қуйидаги тўловлари ҳисобга олинади:
> а) асосий қарз ва фоизлар бўйича тўловлар;
> б) банк фойдасига амалга ошириладиган тўловлар, агар бундай тўловлар кредит шартномаси шартларига мувофиқ қарз олувчининг мажбуриятларига кирса ва/ёки кредит ажратилиши бундай тўловларнинг амалга оширилишига боғлиқ бўлса;
> в) учинчи шахслар фойдасига амалга ошириладиган тўловлар, агар бундай тўловлар кредит шартномаси шартларига мувофиқ истеъмолчининг мажбуриятларига кирса, шунингдек, қуйидаги тўловлар:
> суғурта ташкилоти фойдасига амалга ошириладиган тўловлар, агар суғурта шартномаси бўйича суғурта ҳодисаси юзага келган тақдирда наф олувчи бўлиб банк ҳисобланса;
> қарз олувчининг мажбуриятлари таъминотига қабул қилинган ва гаровга қўювчининг ихтиёрида қоладиган гаров предметини гаров шартномаси бўйича суғурта қилишда қарз олувчи томонидан суғурта ташкилотининг фойдасига амалга ошириладиган тўловлар;
> қарз олувчи томонидан кафолат (кафиллик) олиш учун кафолат берувчига (кафилга), шунингдек гаровга топширилаётган мулкни баҳолаш учун баҳоловчи ташкилотга тўланадиган тўловлар;
> мижозларни жалб қилиш, улар томонидан кредит олиш учун тақдим этилган ҳужжатларни текшириш, ушбу ҳужжатларни банкка топшириш, кредитларни қоплаш ҳисобига банк мижозларидан тўловлар ва пул ўтказмаларини қабул қилиш бўйича банкка хизмат кўрсатадиган ташкилотлар (воситачилар) ҳисобига амалга оширилган тўловлар.
> Банк томонидан КТҚ кўрсаткичининг ҳисоб-китоби кредит шартномаси муддати тугагунга қадар мазкур бандда назарда тутилган барча тўловларни ҳисобга олган ҳолда амалга оширилади.

### cbu_reg_3030:annex1:6
- lex.uz: https://lex.uz/ru/docs/3804290#5789637
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.78
- Pre-filter topics: credit_cost
- Requirement (English, machine translation): When calculating the full amount of a consumer loan, the bank must treat the loan amount as fully transferred at contract signing if the loan can be taken in parts or at chosen times, must calculate insurance costs using the highest current rates and rewards, and must inform consumers that future changes in insurance rates may affect the loan’s full amount.
- Evidence to look for: Loan product terms page or downloadable PDF that states insurance costs are calculated using the highest current rates and includes a notice that future changes in insurance rates may affect the full loan amount.

Original text (Uzbek Cyrillic):

> 6. Кредитнинг тўлиқ қийматини ҳисоблашда қуйидаги шартлар ҳисобга олинади:
> а) агар кредит шартномасига мувофиқ истеъмолчи кредит маблағларини қисмларга бўлиб олиши ёки кредит олиш вақтини танлаш мумкинлиги назарда тутилган бўлса, унда кредит суммаси истеъмолчига кредит шартномасини тузиш вақтида тўлиқ ўтказилган деб ҳисобланади;
> б) кредит олиш истагини билдирган қарз олувчиларга кредит олиш шартлари ҳақидаги маълумотларни тақдим этиш вақтида, кредитнинг тўлиқ қиймати таркибидаги суғурта харажатларини ҳисоблашда суғурта ташкилотларининг жорий даврда амалда бўлган ставка ва мукофот миқдорларидан энг юқориси олинади. Шунингдек, истеъмолчилар келгусида суғурта ташкилотларининг ставка ва мукофот миқдорлари ўзгариши эҳтимоли кредитнинг тўлиқ қийматига таъсир кўрсатиши мумкинлиги тўғрисида хабардор қилинишлари шарт.

### cbu_reg_3030:main:27^1
- lex.uz: https://lex.uz/ru/docs/3804290#6372455
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.78
- Pre-filter topics: collateral
- Requirement (English, machine translation): The bank must explain that guarantors may be held liable under subrogation or subsidiary liability if the borrower fails to repay the loan and interest on time.
- Evidence to look for: A public page (e.g., loan guarantees, collateral, or guarantor information) that states guarantors can be liable for the borrower’s debt under subrogation or subsidiary liability according to law and contract.

Original text (Uzbek Cyrillic):

> 27^1. Банк олдидаги мажбуриятлар таъминоти сифатида мулкини гаровга қўяётган ёки кафил бўлаётган учинчи шахсларга келгусида юзага келиши мумкин бўлган хатарлар, хусусан қарз олувчи томонидан кредит ва унга ҳисобланган фоизлар ўз вақтида тўланмаган тақдирда, кредит бўйича юзага келган қарздорликларни қоплаш учун қонунчиликка ва шартномага мувофиқ учинчи шахснинг гаровдаги мол-мулкига ёхуд кафилнинг мол-мулкига ундирув солидар ёки субсидиар жавобгарлиги тартибида қаратилиши мумкинлигини тушунтириши лозим.

### cbu_reg_3030:main:29
- lex.uz: https://lex.uz/ru/docs/3804290#3805021
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.78
- Pre-filter topics: disclosure
- Requirement (English, machine translation): The bank must provide information to consumers about the risk that the bank may not fulfill its obligations under a consumer credit contract, including any penalties and the possibility of increased consumer expenses.
- Evidence to look for: Consumer credit product page or terms and conditions section that states the bank’s possible non‑performance risks, applicable penalties (fines, interest) and that the consumer’s costs may increase.

Original text (Uzbek Cyrillic):

> 29. Банк истеъмолчи кредит шартномаси бўйича ўз мажбуриятларини лозим даражада бажармаслиги билан боғлиқ таваккалчиликлар тўғрисида, шу жумладан истеъмолчига нисбатан мажбуриятларни бузганлиги учун қўлланиладиган неустойка (жарима, пеня) ва уларнинг натижасида истеъмолчининг харажатлари суммаси ошиши эҳтимоли тўғрисида ахборот беради.

### cbu_reg_3030:main:35^3
- lex.uz: https://lex.uz/ru/docs/3804290#7816808
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.78
- Pre-filter topics: tariffs_fees, terms_offer
- Requirement (English, machine translation): The bank must not pre‑set any consumer choice indicators or pre‑fill credit‑parameter fields in its remote service interfaces, and must allow the consumer to independently select options and enter information.
- Evidence to look for: Inspect the publicly accessible online loan application page (HTML/PDF) and verify that no checkboxes or radio buttons have the "checked" attribute by default and that input fields for credit amount, term, and income are empty (no preset "value" attribute).

Original text (Uzbek Cyrillic):

> 35^3. Банклар томонидан молиявий хизматлар кўрсатиш жараёнида, шунингдек банкнинг масофавий хизмат кўрсатиш тизимлари орқали хизматлар кўрсатилаётган пайтда қуйидаги ҳолатларнинг жорий этилишига йўл қўйилмайди:
> истеъмолчининг хоҳиш-иродасини ифодаловчи ҳар қандай белгиларни (масалан, белги қўйиш майдончалари, силжитма тугмалар ва шунга ўхшашларни) олдиндан ўрнатиб қўйиш ёки танлаб қўйиш;
> кредит параметрлари кўрсатилган майдончаларни, шу жумладан кредит суммаси, муддати ҳамда тегишли аризадаги истеъмолчининг даромади тўғрисидаги маълумотларни олдиндан тўлдириш.
> Бунда агар банк истеъмолчига тегишли танловни таклиф қилса, унга кредитни расмийлаштириш жараёнида мустақил равишда белгини қўйиш, кредит параметрларини мустақил белгилаш ва бошқа майдончаларни тўлдириш имконияти берилиши керак (масалан, кредит бюросидан кредит ҳисоботини сўраш, реклама тусидаги ахборотни юбориш, масофавий молиявий хизматни улаш, банк хизматларининг умумий шартлари билан танишганлигини тасдиқлаш, банк тарифларини қабул қилиш ва шунга ўхшаш белгилар).

### cbu_reg_3030:main:36^11
- lex.uz: https://lex.uz/ru/docs/3804290#4749299
- Proposed check_type: required_document
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.78
- Pre-filter topics: tariffs_fees
- Requirement (English, machine translation): The loan contract must specify the type of interest rate, the principal amount, and the method of interest payment (differential or annuity).
- Evidence to look for: Find the publicly posted loan agreement (e.g., PDF or web page) and confirm it includes clauses stating the interest rate type (fixed or variable), the loan principal amount, and the interest payment method (differential or annuity).

Original text (Uzbek Cyrillic):

> 36^11. Кредитдан фойдаланганлик учун фоиз ставкаси тури (ўзгармас ёки ўзгарувчи фоиз ставкаси) ҳамда кредитнинг асосий суммаси ва фоизларини тўлаш усули (дифференциал ёки аннуитет) томонларнинг ўзаро келишувига мувофиқ кредит шартномасида назарда тутилиши керак.

### cbu_reg_3030:main:36^2
- lex.uz: https://lex.uz/ru/docs/3804290#4427611
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.78
- Pre-filter topics: tariffs_fees
- Requirement (English, machine translation): The bank must not set different tariffs for its services based on whether the payment is made in cash or cashless.
- Evidence to look for: Tariff page(s) showing a single price for each service without separate cash and cashless rates, or a statement that rates are the same for all payment methods.

Original text (Uzbek Cyrillic):

> 36^2. Банк томонидан тўлов шаклига қараб (нақд пул билан ёки нақд пулсиз ҳисоб-китоблар) банк хизматлари учун ҳар хил нархлар (тарифлар) белгилаш тақиқланади.

### cbu_reg_3030:main:37^1
- lex.uz: https://lex.uz/ru/docs/3804290#7643475
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.78
- Pre-filter topics: collateral
- Requirement (English, machine translation): The bank must allow a borrower to use the funds from a deposit pledged as collateral to repay a loan at any time and the borrower must notify the bank at least one month before the intended deposit withdrawal for repayment.
- Evidence to look for: Deposit or loan terms page stating that pledged deposit funds can be used for loan repayment at any time and that the borrower must give at least one month notice before withdrawing the deposit for repayment.

Original text (Uzbek Cyrillic):

> 37^1. Қарз олувчи кредит бўйича гаровда турган ўзининг депозитидаги (омонатидаги) маблағларини кредит шартномаси даврининг хоҳлаган вақтида депозит (омонатнинг) амал қилиш муддатидан қатьи назар, мазкур кредитни қайтариш учун йўналтириш ҳуқуқига эга.
> Бунда, қарз олувчи кредит бўйича гаровда турган ўзининг муддатли депозитидаги (омонатидаги) маблағларини шартномада кўрсатилган депозит (омонат) муддати тугагунга қадар кредитни қайтариш учун йўналтирмоқчи бўлса, у бу ҳақда банкни депозитни (омонатни) қайтаришни мўлжаллаётган санадан камида бир ой олдин хабардор қилиши лозим.

### cbu_reg_3030:main:37^2
- lex.uz: https://lex.uz/ru/docs/3804290#7643486
- Proposed check_type: key_info
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.78
- Pre-filter topics: tariffs_fees
- Requirement (English, machine translation): If a borrower pays more than the scheduled amount, the bank must allocate the excess to the loan principal and recalculate the loan unless the contract specifies otherwise.
- Evidence to look for: Loan product page or downloadable loan agreement PDF that states that overpayments are applied to the principal and that the repayment schedule will be updated accordingly.

Original text (Uzbek Cyrillic):

> 37^2. Қарздордан кредитнинг жорий тўлови учун кредитни қайтариш жадвалида белгиланган суммага нисбатан кўп маблағ келиб тушса, у ҳолда банк келиб тушган маблағнинг ортиқча қисмини қарз олувчининг кредитининг асосий қарзини сўндиришга йўналтиради ҳамда кредит суммасини қайта ҳисоблайди, агар шартномада бошқача тартиб белгиланмаган бўлса.
> Агар кредитни қайтариш жадвали расмийлаштирилгандан сўнг кредит бўйича молиялаштиришни бошлаш муддатлари ёки шартномада кўзда тутилган ўзгарувчан фоиз ставкаси ўзгариши, кредит шартномасининг шартлари томонлар ўртасида қайта кўриб чиқилиши (шу жумладан, кредитнинг реструктуризация қилиниши), қарз олувчи томонидан кредит қисман муддатидан олдин сўндирилиши муносабати билан кредит бўйича тўловларни амалга ошириш саналари ва муддатлари ёки оралиқ кредит тўловларининг миқдорлари ўзгарганда банк кредитни қайтариш жадвалини янгидан расмийлаштириб, қарз олувчига тақдим қилиши лозим.
> Бунда, кредитни қайтариш жадвали янгидан расмийлаштирилиши билан ундан олдин мавжуд бўлган кредитни қайтариш жадвали ўз кучини йўқотади. Ушбу қоида кредит шартномасида қайд этилиши шарт.

### law_state_language:art:21
- lex.uz: https://lex.uz/ru/docs/121051#121254
- Proposed check_type: uz_version
- Checkable from public website (LLM): yes
- LLM confidence (self-reported): 0.78
- Pre-filter topics: state_language
- Requirement (English, machine translation): Enterprises must provide product manuals, instructions and labels in the state language (Uzbek) as well as in other languages.
- Evidence to look for: Find Uzbek‑language versions of product manuals, instruction sheets or label PDFs (e.g., downloadable brochures, tariff documents) linked from the bank's public product pages.

Original text (Uzbek Cyrillic):

> 21-модда.
> Корхоналарда ишлаб чиқариладиган маҳсулот давлат тилидаги ва бошқа тиллардаги ёрлиқлар, йўриқномалар, этикеткалар билан таъминланади.

## Pre-filtered but judged not checkable (44)

| clause_id | reason (LLM) | confidence |
|---|---|---|
| cbu_reg_3030:annex1:1 | The clause merely defines terms and does not require the bank to publish any information on its public website. | 0.99 |
| cbu_reg_3030:annex1:11 | The obligation relates to responding to customer inquiries, which cannot be verified from publicly available website pages or documents. | 0.95 |
| cbu_reg_3030:annex1:3 | The clause governs internal accounting entries that are not publicly disclosed, so compliance cannot be verified from the website alone. | 0.95 |
| cbu_reg_3030:annex1:4 | The required disclosure is made to individual borrowers during credit negotiations and is not necessarily published on the public website. | 0.90 |
| cbu_reg_3030:annex1:5 | The clause concerns internal calculation methods and insurance payment details that are not disclosed on public web pages. | 0.95 |
| cbu_reg_3030:annex1:8 | The calculation method and use of software tools are internal processes not disclosed on the public website. | 0.95 |
| cbu_reg_3030:annex1:preamble | The clause pertains to internal calculation methods that are not publicly disclosed on the website. | 0.92 |
| cbu_reg_3030:annex4:2 | The required information pertains to internal complaint handling procedures that are not disclosed on the public website. | 0.95 |
| cbu_reg_3030:main:1 | The clause only provides definitions and does not impose any publishable obligation that can be verified on the public website. | 0.95 |
| cbu_reg_3030:main:11 | Agreement on communication channels is a private contractual step not observable on the public website. | 0.90 |
| cbu_reg_3030:main:15 | Compliance requires verifying the website meets the detailed external regulation, which cannot be fully assessed from the public site alone. | 0.90 |
| cbu_reg_3030:main:18 | The required functionality and access to personal cabinet information can only be verified behind a login or within the mobile app, not from publicly accessible pages. | 0.90 |
| cbu_reg_3030:main:21 | The clause concerns the bank's keyword usage in contextual ads, which cannot be observed from the public website alone. | 0.95 |
| cbu_reg_3030:main:22 | Verifying that the bank's website does not resemble another credit organization's site requires comparison with external sites, which cannot be assessed from the bank's public website alone. | 0.95 |
| cbu_reg_3030:main:26 | The clause requires oral provision of information, which cannot be verified from the public website alone. | 0.95 |
| cbu_reg_3030:main:27 | The required pre‑contractual information may be given directly to the consumer in person or other non‑public ways, so compliance cannot be verified solely from the bank's public website. | 0.90 |
| cbu_reg_3030:main:3 | Font type and the use of Microsoft Word cannot be verified from publicly accessible HTML or PDF pages. | 0.92 |
| cbu_reg_3030:main:33 | The prohibited practices are internal actions that are not disclosed on the public website, so compliance cannot be verified from publicly available pages. | 0.95 |
| cbu_reg_3030:main:35 | Many obligations (e.g., internal assessment of repayment ability, pre‑contract information per sections 27‑29, and prohibition of unilateral contract changes) are not disclosed on public webpages and require access to contracts or internal procedures. | 0.86 |
| cbu_reg_3030:main:35^1 | The clause regulates internal banking practices that are not required to be published on the bank's public website. | 0.97 |
| cbu_reg_3030:main:36^10 | The required information is posted only in the borrower’s personal online cabinet, which is not publicly accessible. | 0.97 |
| cbu_reg_3030:main:36^5 | The clause concerns internal practices about choice of insurer or appraiser, which are not disclosed on public website pages. | 0.85 |
| cbu_reg_3030:main:36^6 | The clause mandates specific content and formatting within individual credit contracts, which are private documents not publicly accessible on the website. | 0.95 |
| cbu_reg_3030:main:37^4 | The actions concern internal collateral removal procedures and register updates, which are not required to be published on the bank's public website. | 0.95 |
| cbu_reg_3030:main:39 | The requirement concerns on‑site information, staff identification badges, and contract‑signing facilities, which are not reflected on the public website. | 0.95 |
| cbu_reg_3030:main:47 | Information about the placement of contact details on branch stands and staff explanations cannot be verified from the public website alone. | 0.92 |
| cbu_reg_3030:main:9 | The clause requires individualized written information to be supplied on request, which is not publicly disclosed on the website. | 0.97 |
| cbu_reg_3030:resolution:2 | Compliance depends on internal timing of implementation, which cannot be verified from the public website. | 0.97 |
| law_state_language:art:1 | The clause does not impose a specific, verifiable obligation on the bank that can be assessed via its public website. | 0.90 |
| law_state_language:art:10 | The clause concerns internal accounting and financial documents that are not necessarily published on the public website. | 0.90 |
| law_state_language:art:11 | The clause pertains to judicial language procedures, which are not disclosed on the bank's public website. | 0.95 |
| law_state_language:art:12 | The clause concerns the language of notarial documents, which is not information typically disclosed on a bank's public website. | 0.90 |
| law_state_language:art:13 | The clause pertains to internal civil‑status and identity documents, which are not required to be posted on the bank's public website. | 0.95 |
| law_state_language:art:16 | The clause concerns television and radio broadcasts, which are not reflected on the bank's public website. | 0.95 |
| law_state_language:art:18 | The clause concerns postal‑telegraph service language requirements, which are not disclosed on the bank's public website. | 0.95 |
| law_state_language:art:19 | The clause applies to all internal documents, many of which are not publicly posted, so compliance cannot be verified from the public website alone. | 0.90 |
| law_state_language:art:2 | The clause concerns constitutional language rights, which cannot be verified solely from the bank's public website. | 0.92 |
| law_state_language:art:23 | The bank's public website does not publish the texts of Uzbekistan's international agreements, so compliance cannot be verified online. | 0.95 |
| law_state_language:art:4 | The clause sets national language policy and does not impose a specific, verifiable obligation on the bank, so it cannot be assessed via the bank's public website. | 0.95 |
| law_state_language:art:5 | The clause concerns establishment of minority-language preschool institutions, which is not information typically published on a bank's public website. | 0.95 |
| law_state_language:art:6 | The clause concerns education language rights and does not impose obligations on banks, so it cannot be verified on the bank's website. | 0.95 |
| law_state_language:art:8 | The clause pertains to state authority documents, not to information that a bank must display on its public website, so it cannot be verified from the bank's site. | 0.95 |
| law_state_language:art:9 | The clause pertains to the language use of state bodies, which cannot be verified through the bank's public website. | 0.99 |
| law_state_language:enactment:preamble | The clause concerns a parliamentary decision about the state language law, not a specific obligation of the bank. | 0.95 |

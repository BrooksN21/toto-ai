# Sports-v2 coverage4998: точная локальная причина

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906. 2026-09-06T11:28:58.026504+00:00.
Контекст только: предыдущий `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/context.md`, exactseed и boundGOALcapture, узкие функции pipeline. Без provider/network/DB/training/replay/tests/code/jobs/auth/main-memory/VCS действий; единственная запись — этот файл. Нет своего фонового процесса.

##Ответ владельцу
**Не «просто не обучено»: GOAL schedule collection завершился `source_failed: GOAL API duplicate event identity conflicts`.** Boundreport:7 HTTP200 запросов `/fixtures/date/2026-09-05`,candidate_count0,unresolved15,budget_exhausted=false. Это один общий сбой коллекции, а НЕ доказательство отсутствия всех15целевыхматчей уGOAL.
Ни одинматч не получил GOALfixture/team binding; запросы team-history не начались: history_source_count0,sports_eligible_count0. Coverage записал target_fixture_missing; importer построил missingevent с двумя пустымиhistorywindows; probabilitygate вернул sports_history_missing. Все15sports/candidate probabilities точно равныBK,blend_weight0.
`validation_failures=[]` — отсутствие объявленныхglobalvalidationошибок вseed, НЕ проверка наличия спортивнойистории/статистическойпредсказательности. ModelstatusINSUFFICIENT_EVIDENCE,statusNOT_ACTIVATED. Получился валидируемый fallback-артефакт, а не провереннаяспортивнаяаналитика. Здесь не выполнялась повторная полнаяprojectvalidation/DBhydration.

##Точные sourcebindings
- Pinned `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/parallel-challenger/sports-seed/sports_probability_shadow_4998_08da2cb616e108b8.json`: fileSHA `9c2489b5cf65289227f6df794182fe71aa37f3b4ffb840c6111e8a1de1426fbd`; artifactSHA `08da2cb616e108b87b620ef5e4d2091c326174172b53524c975d4c23a05e632f`; as_of `2026-09-06T09:34:19.081148+00:00`; snapshotrun/content `7e7bbdd815376fc6f9482032be34f3108b8122caff412ef7b34bf7ef34cfc71e`.
- Marker `/Users/turshevr/toto-ai/reports/sports-analytics/4998/goal-auto/current.json`: capture `2026-09-06T09:34:19.081148Z`,PAPER_ONLY_COVERAGE_PROBE_READY. READY означает сохранённый paperprobe,неusablepredictor.
- Coverage `/Users/turshevr/toto-ai/reports/sports-analytics/4998/goal-auto/captures/20260906T093419081148Z/coverage-summary.json`: actualfileSHA `979ffc7bd308ccd76df368a82d6a6833000b714d2cdb0da6ebe64975da7cf38d`; markerdeclared `979ffc7bd308ccd76df368a82d6a6833000b714d2cdb0da6ebe64975da7cf38d` — совпадают.
- Schedule `/Users/turshevr/toto-ai/reports/sports-analytics/4998/goal-auto/captures/20260906T093419081148Z/schedule/schedule-source-candidates.json`: actualfileSHA `70a9b500682c4e1ecb2fc7e1770a069c960ce37d80ccb722b0704de05bf36e67`; markerdeclared `70a9b500682c4e1ecb2fc7e1770a069c960ce37d80ccb722b0704de05bf36e67` — совпадают. Records:15 GOALsource_failed с однойошибкой плюс15общихnot_found.
- Вschedule Sofa0: collection применяет пустойstubfetcher,это не liveSofaoutage. TheSportsDBdisabled_missing_key. GOALне показалauth/quotaerror:remaining931 **по старомуcapture**,неcurrentquery. Секреты не читались.
-7rawsnapshots присутствуют под `/Users/turshevr/toto-ai/reports/sports-analytics/4998/goal-auto/captures/20260906T093419081148Z/schedule/goal-api-v1/snapshots/`. Report не называет конкретный duplicatefixtureID/поле; rawparser не переисполнялся. Не утверждаю,что duplicate относится к одной из15целей или уже исправлен.
- Дополнительную queueSHA-связь не объявляю проверенной: sourcecollector использует отдельный queuehashcontract,не обычныйwholefileSHA. Проверка этого вспомогательногоhash была остановлена без измененияфайлов; основнойвывод опирается на совпавшиеfilehash coverage/schedule и exactseed.

##15событий — одинаковый первичный блокер
Имена изboundcoverage; №пользовательский / нулевойevent_order,не новыйidentityreview.

|№ /order|targeteventID|Матч|coverage → seed|
|---|---|---|---|
|1 / 0|180633|Динамо Москва — Спартак Москва|target_fixture_missing → sports_history_missing|
|2 / 1|180634|Балтика — Локомотив Москва|target_fixture_missing → sports_history_missing|
|3 / 2|180635|Малага — Леванте|target_fixture_missing → sports_history_missing|
|4 / 3|180636|Алавес — Осасуна|target_fixture_missing → sports_history_missing|
|5 / 4|180637|Эспаньол — Севилья|target_fixture_missing → sports_history_missing|
|6 / 5|180638|Болонья — Сассуоло|target_fixture_missing → sports_history_missing|
|7 / 6|180639|Ювентус — Милан|target_fixture_missing → sports_history_missing|
|8 / 7|180640|Андерлехт — Генк|target_fixture_missing → sports_history_missing|
|9 / 8|180641|СК Беверен — Ауд-Хеверле Левен|target_fixture_missing → sports_history_missing|
|10 / 9|180642|Франс Борайнс — Локерен-Темсе|target_fixture_missing → sports_history_missing|
|11 / 10|180643|Локомотив Пловдив — Черно Море|target_fixture_missing → sports_history_missing|
|12 / 11|180644|ОФИ — Кифисия|target_fixture_missing → sports_history_missing|
|13 / 12|180645|Панатинаикос — ПАОК|target_fixture_missing → sports_history_missing|
|14 / 13|180646|Оцелул — Рапид Бухарест|target_fixture_missing → sports_history_missing|
|15 / 14|180647|Коджаелиспор — Самсунспор|target_fixture_missing → sports_history_missing|

Длякаждого coverage: provider_fixture_id,provider_home_team_id,provider_away_team_id,target_starts_at=null; sources=[],sports_eligible=false. Длякаждогоseed: feature_status=missing,model_feature_scope=non_venue_unavailable; home/away fixture_count,goals,last5_form_points,points_per_game,rest_days,standing,venue_played,venue_wdl,wdl=null. Orientationpin=null,sourcepayloadhashes=[],requestfingerprints=[],sports_model=null,expectedgoals=null,venueconfidence0. Не дело только вstanding/venuecount: **истории вообще не получены**.
Reviewed schedule15/15,включаяevent9,не равноGOALhistory15/15. Ledgerkickoff не предоставляетGOALteamID иформу; нельзя подставитьSofaIDвGOALID.

##Новыеseeds тоже0/15
Все7локальныхJSON проверены поfields:coverage0/fallback15,validation_failures=[],same reasons,пустыеsources,blend0,BKfallback. Новыхusable sports probabilities нет.

|Suffix|as_ofUTC|coverage/fallback|fileSHA256|
|---|---|---|---|
|08da2cb616e108b8|2026-09-06T09:34:19.081148+00:00|0/15|`9c2489b5cf65289227f6df794182fe71aa37f3b4ffb840c6111e8a1de1426fbd`|
|aada3a2193ff5359|2026-09-06T09:49:22.396075+00:00|0/15|`1d47690232e0516017bdc7d408337f4e5afbab6b5f4cf8b6f4d73330e346820a`|
|1961696791477f00|2026-09-06T10:04:31.375037+00:00|0/15|`1134f529f1aab42f99ed8efeb08a49d1604c180450f4fda6e9ada0a86f32c5e1`|
|2973f933452381b0|2026-09-06T10:19:41.697927+00:00|0/15|`0e47c20c558dfbe8e6c5c06e557a0312f73d930cf50fe88ac989214db181969d`|
|176c512ba9861dd8|2026-09-06T10:34:51.773310+00:00|0/15|`49b09782a5b935b1e08f520971ba41376cb938c5b466683d1b38a5254b75b044`|
|66507dfbf7064e90|2026-09-06T11:00:31.569442+00:00|0/15|`fc65bd2b3591821993b0ceeb68d6b01164c204e3d62c1a87553f6b6bdb01a184`|
|d9e4bdb68400db97|2026-09-06T11:15:45.573445+00:00|0/15|`75b84c8c156650765d6594487fa41de3b41a7b81fc56afb22252fc13b92ad345`|

Почему: `goal_probe_collection.py:42–60 ensure_goal_probe_input` возвращает сохранённуюcollection при наличииcurrent.json,включаянулевуюcoverage. Marker всё ещё ссылается на12:34:19MSKcapture. CLI4432–4469 переиспользуетcoverage сновымas_of,4540–4555 выпускаетновыйv2seed. Позднийgenerated_at/BKsnapshot не означаетновуюhistorycollection. Поpreviouscontext wrapperpinned08da2c; ничего не переключалось.

##Реальныеpipelinegates
1. `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/goal_probe_collection.py:164–182`:нетGOALschedule_row→fallback. Только сfixture/home/awayID/kickoff начинаетсяfetch_team_results(limit10) дляобеихсторон,183–225.
2. `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/goal_probe_research.py:213–274,305–336`:exactbinding,обеhistorysources,validatedpath/hash/as_of; иначеmissingevent. История строго доas_of/targetkickoff,terminalstatus иправильнаякоманда. Не подставлятьобщийaggregate безevent-localprovenance.
3. `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/probabilities.py:467–525`:pre-match,обеwindows,orientationpin same+exactIDs/fingerprint,chronology,venuehistory. Сейчас перваяпричина послеtime —sports_history_missing,доmodel-qualityэтапа.
4. `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v2.py:109–125,184–195`:basefallbackсохраняется;football+complete,обеwindows,**минимум2home-venueматча хозяев и2away-venueматча гостей**. ДалееvenueWDL+smoothedPoissongoals,prior3,maxblend0.2,disagreementlimit0.45. Положительнаяcoverage остаётсяEXPERIMENTAL_UNTRAINED_V2,неprofitproof.
5. O1descriptiveevidence/G1optimizer не создаютmissingprovider/historybytes,не повышаютeligibility. Syntheticcode-tests не заменяют statisticalvalidation sportsforecasts.

##Минимальныйследующийшаг — НЕ выполнен
Не обучение и не смена0/15seed. Отдельно разрешить **узкую offline raw-identityдиагностику сохранённых7GOALpages уже принятымparser**:назвать exactduplicateID/поля,проверить наличиепригодныхbindings для15целей. Безnetwork/forecast/replayпакетов. Еслиистинныйconflictсохраняется —failclosed,неослаблятьguard.
Принятыйgenericfix: `/Users/turshevr/toto-ai/knowledge/goal_pagination_identity_boundary.md`; receipt `/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/GOAL_PAGINATION_ADOPTION_RECEIPT_20260906.json`,statusAPPLIED_VERIFIED_UNCOMMITTED;sourceafterSHA73d6d9e6185c35fab07565ce0566c15f869ad19f907547ab70f89bed5b28ccbb. Исключаеттолькоtop-levelupdatedAt/capturebookkeeping изduplicateidentity,остальныеrawfields конфликт-чувствительны. Capture12:34 раньшеadoption~12:54: **возможнаустаревшаяparsererror,но исправлениеэтогоexactcapture не доказано**. Fixне обновляетcachedmarker.
Послеуспешногоbinding нужныотсутствующиеhome/awayhistorysources длякаждогоusableevent (для15 —30),сдостаточнымvenuecount/chronology. Сбор/newimmutablecapture —отдельнаяразрешённаяnetworkзадача. Нельзяудалять/переписыватьcurrent.json/старыеhashes. Далее новыйявноboundresearchsnapshot/seed,dryfieldvalidation,отдельноsidecarinputрешение; statisticalvalidationотдельна.

DONE:корневаяпричина,15eventtable,7seedcomparison,точныеsourcefilebindings. BLOCKER:cachedsource-wideduplicatefailure→0GOALbindings/0histories;exactrawconflictID/fieldнеустановлен. NEXT:parentполучаетэтотфайл и решаетузкуюofflineдиагностику. Mainmemory/jobs/authнеизменены;никакихобщих«необучено»вместофактов.

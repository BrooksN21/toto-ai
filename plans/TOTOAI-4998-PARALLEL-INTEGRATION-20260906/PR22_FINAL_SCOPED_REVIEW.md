# PR22 final scoped review — ACCEPT

2026-09-06 18:54:32 UTC. Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906.

**Перечисленные пробелы ревью закрыты; блокирующих замечаний нет.** Точный PR22 head **71afde0050f37cf9a208831d64da403b0605fef2**, base **a59e3e54a1698efe60a862bbab681996c06ff8f7** допустим для отдельно разрешённой финализации merge при обычной проверке текущих remote refs/checks/protection и сохранности checkout. Это составной вывод на основе [MERGE_READINESS](/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/MERGE_READINESS_20260906.json) + настоящего узкого ревью, не повторное ревью 121 файла и не заявление о прохождении всей suite.

## Закрытые пробелы

| Объём | Решение и основание |
| --- | --- |
| Carry-in a17: storage.py/test + domain.py | ACCEPT. Поиск same-identity сохраняет as_of; перед semantic equality проверяются исходные hashes. Source evidence, deadline, history size и sporting payload остаются связанными; исключаются replay diagnostics. Транзакционный rollback сохранён. |
| scripts/project-git + новые worktree tests | ACCEPT. Проверены actual hunks attestation/canonical paths/backlinks/common-dir, запреты на overrides/write commands. 18 synthetic wrapper tests PASS, без bare Git fixtures. |
| schedule_evidence_admin.py/test | ACCEPT. Только добавление com.cy в multipart suffixes; проверка различимых издателей проходит. |
| targets.py/test | ACCEPT. Недостаточные значения пула дают unavailable, BK сохраняется; полностью доступные значения проходят прежнюю finite-positive проверку. |
| sports_stats_cli.py test | ACCEPT. Дополнительная проверка offline backfill help; acceptance самой реализации — прежняя цепочка. |

Все десять проверенных working files побайтно совпали с blobs указанного head. Хеши в [JSON](/Users/turshevr/.codex/worktrees/ab34/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/PR22_FINAL_SCOPED_REVIEW.json). Runtime02/observer03 повторно не ревьюились: их точные независимые acceptance/hash-bindings переиспользованы из readiness.

## Найденные независимые acceptance anchors

- **90min:** [HISTORY90_INDEPENDENT_REVIEW.md](/Users/turshevr/.codex/worktrees/a7aa/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/HISTORY90_INDEPENDENT_REVIEW.md), SHA `6101edac61a4f58bcd6f1095d46d67afd9e593d7278b5bfd1e6c26996c97feea`. Его probe SHA `0868c6de…` подтверждён; все пять candidate files и patch `dc150fdc…` совпали с manifest probe. Исходный independent result: 79 PASS, два SQLite-теста заблокированы — не 81 PASS. Raw/seed evidence заново не читалась/не исполнялась.
- **G1 profile:** [точный independent ACCEPT](/Users/turshevr/.codex/worktrees/ab34/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/G1_EVALUATION_PROFILE_INDEPENDENT_REVIEW.json), SHA `1a64cf9f686043e4ff51cf75f727e4166d50fb7685da328d4e4358defd60a549`, patch `c3fe388c…`. Current source/test совпали; original 14 synthetic PASS/Ruff. Это принятие cap delta 50000→65536, не гарантия завершения dense search.
- **Cache:** [atomic review](/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/CACHE_ATOMIC_INDEPENDENT_REVIEW.json) (18 PASS, REQUEST_CHANGES из-за directory fsync) → [fsync-only ACCEPT](/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/CACHE_DURABLE_INDEPENDENT_REVIEW.json) (4 PASS). Hash-chain `75bd7b86… → delta11b2d765… → fulle914a097…` подтверждён; current source `703d7e8c…` и test `3bc0e70b…` совпали с финальным manifest. Сохраняется именно составное закрытие finding, не подмена независимого ревью publication-хешем.

## Свежая ограниченная проверка

**144 + 18 PASS**, Ruff **14 Python-файлов PASS**. Pytest ограничен 25 с, Ruff 15 с; только main imports и свежие temporary fixtures, SQLite только временная/in-memory, сеть/live DB/запись в main запрещены.

Первый запуск: 144 PASS / 18 FAIL / 1 deselected, 3.29 с. Все 18 FAIL возникли до исполнения wrapper из-за собственного harness `Path cwd != str cwd`. Исправлено только сравнение cwd в review harness; повторены только эти 18 случаев: **18 PASS, 4.21 с, blocked=[]**. Первый запуск и ограничения не скрыты; source fixes не было. Импортная попытка socket.bind была заблокирована.

Не запускались четыре legacy bare-Git теста, перечисленные в JSON/readiness. Отдельно исключён неизменённый multiprocessing `test_concurrent_apply_is_locked_and_never_loses_updates`, не относящийся к com.cy hunk. **Нет утверждения whole-suite PASS или GitHub CI PASS.**

## Граница финализации

Локальный HEAD всё ещё exact71afde0. Main memory уже содержит новый preflight PASS от21:46:44МСК; это только прочитанный operational handoff, не live проверка. Следующий metadata commit требует отдельной compatibility-проверки; новые source changes этим ACCEPT не покрываются.

Финализатор должен сверить текущие remote base/head/checks и разрешённый merge method, согласовать checkout alignment с владельцем операций и сохранить dirty ledger, raw/evidence, worktrees. F4 остаётся изолированным и не включается. Этот reviewer не менял main/исходники/AGENTS/skills/ветки/jobs/consent и ничего не публиковал/не сливал.


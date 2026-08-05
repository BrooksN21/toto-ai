# Аудит сбоя автоматики 4952

Аудит завершён. Правок, кроме этого контекстного файла, не делал.

## Точные причины

### 1. `data/raw` превратился в `/data/raw`

- launchd plist не содержит `WorkingDirectory`:  
  `/Users/turshevr/toto-ai/reports/rehearsal/evening-4952/totoai-scheduler.plist`
- wrapper не выполняет `cd` в проект:  
  `/Users/turshevr/toto-ai/reports/rehearsal/evening-4952/run-scheduler.sh`
- `prepare-drawing` имеет относительный default `data/raw`:  
  `/Users/turshevr/toto-ai/src/toto_ai/cli.py:2112`
- scheduler не передаёт `--raw-cache-dir`:  
  `/Users/turshevr/toto-ai/src/toto_ai/runner/scheduler.py:1062-1087`

При launchd-подобном `cwd=/` путь закономерно стал `/data/raw`. Это подтверждает первый status:

`/Users/turshevr/toto-ai/reports/rehearsal/evening-4952/runs/4952/20260722T151508736546Z-cffac183/status.json`

При этом нужный файл существовал здесь:

`/Users/turshevr/toto-ai/data/raw/drawing_11970.json`

### 2. Preflight проигнорировал прогретый API-Sports cache

Scheduler жёстко передаёт preflight:

```text
--cache-root <уникальный run>/work/preflight/cache
```

Источник:

`/Users/turshevr/toto-ai/src/toto_ai/runner/scheduler.py:1081-1082`

Это новый пустой каталог. Прогретый утром cache находился здесь:

`/Users/turshevr/toto-ai/data/external-cache/api-sports/`

Из-за cache miss preflight пошёл в сеть. Запросы не удались, после чего все даты получили `failed`, а существующие pins были отклонены. Это подтверждает:

`/Users/turshevr/toto-ai/reports/rehearsal/evening-4952/runs/4952/20260722T152624657022Z-dd7b24c8/status.json`

Важно: изолированный cache нужно оставить для **fallback/final**, чтобы они получали свежие данные. Ошибка — его использование именно в **preflight**.

## Почему тесты не поймали

- `test_scheduler_wrapper_securely_sources_env_and_plist_only_runs_wrapper` запускает только `--dry-run` из текущего каталога.
- `test_command_phase_preflight_runs_mandatory_prepare_drawing` полностью подменяет `subprocess.run` и не проверяет cache-пути.
- `test_scheduler_cli_real_production_parser_and_capture_are_offline` вообще переопределяет `_preflight`.

Реального запуска из `cwd=/` не было.

## Минимальное надёжное исправление

1. Добавить в `SchedulerPlan` абсолютный `project_root`.
2. Передавать preflight явно:
   - `--raw-cache-dir <project_root>/data/raw`;
   - `--cache-root <project_root>/data/external-cache/api-sports`.
3. Запускать дочерние процессы с `cwd=project_root`.
4. Добавить `WorkingDirectory=project_root` в plist и `cd project_root` в wrapper как дополнительную защиту.
5. Не менять run-scoped cache у fallback/final.
6. Перегенерировать scheduler plan/plist после изменения схемы.

## Обязательные новые тесты

В `/Users/turshevr/toto-ai/tests/test_runner_scheduler.py`:

- `test_prepare_command_uses_absolute_raw_and_reusable_provider_cache`
- `test_package_phases_keep_run_isolated_cache`

В `/Users/turshevr/toto-ai/tests/test_scheduler_operational_artifacts.py`:

- `test_evening_scheduler_preflight_succeeds_from_launchd_root_cwd`
- `test_evening_launch_agent_sets_project_working_directory`

Первый должен запускать настоящий generated preflight через `subprocess` с `cwd="/"`, прогретыми локальными cache-файлами и запрещённым HTTP. Именно такой тест воспроизведёт оба дефекта.

# invoice_quote_filler v0.2.1: Codex finish checks runbook

## 1. Назначение script

`scripts/run_codex_finish_checks.py` запускает стандартные read-only проверки и
печатает компактный `CODEX_FINISH_REPORT` для передачи в ChatGPT.

Script нужен, чтобы Codex и Игорь не собирали финальный статус вручную из
разрозненных команд, screenshots и пересказов.

## 2. Когда запускать

Запускать после завершения задачи, перед финальным отчётом, commit или push,
если нужно быстро проверить состояние repo и получить готовый текстовый блок.

Для маленьких задач обычно достаточно `--mode fast`. Перед commit/push или после
изменений с большим blast radius лучше запускать `--mode full`.

## 3. Разница `--mode fast` и `--mode full`

`--mode fast` запускает:

- `mypy`;
- `ruff check`;
- `black --check .`;
- `git diff --check`;
- `scripts/build_repo_handoff.py`.

`--mode full` дополнительно запускает полный `pytest` перед остальными
проверками.

По умолчанию ни `--mode fast`, ни `--mode full` не запускают quote smoke.
Canonical quote smoke запускается только по явному флагу
`--include-quote-smoke`.

## 4. Команды запуска

Daily / quote workflow finish command:

```powershell
.\scripts\finish_quote_workflow.ps1
```

Эта короткая команда эквивалентна:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_codex_finish_checks.py --mode fast --include-quote-smoke
```

Wrapper запускает только finish checks и existing synthetic-only quote smoke.
Он не принимает и не читает real client files. Полный
`CHECKED_QUOTE_SMOKE_REPORT`, `CODEX_FINISH_REPORT`, nested `CHATGPT_HANDOFF` и
`Quote workflow` block печатаются без сокращений.

Fast mode:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_codex_finish_checks.py --mode fast
```

Full mode:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_codex_finish_checks.py --mode full
```

Fast mode with quote smoke:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_codex_finish_checks.py --mode fast --include-quote-smoke
```

`--include-quote-smoke` запускает existing synthetic-only helper:

```powershell
.\scripts\smoke_checked_quote_launcher.ps1
```

Finish report печатает полный `CHECKED_QUOTE_SMOKE_REPORT` и добавляет в
`Checks` строку `quote smoke: pass` или `quote smoke: fail`.

Smoke helper создаёт только synthetic temp CSV/XLSX outside Git и удаляет temp
`.xlsx` после проверки. Smoke PASS не является commercial approval и не заменяет
manual Igor check / Human Approval before sending to client.

Те же ограничения действуют для `finish_quote_workflow.ps1`: smoke PASS не
разрешает отправку draft клиенту. Manual Igor check и отдельный Human Approval
before sending to client остаются обязательными.

## 5. Что отправлять ChatGPT

Отправлять весь блок между:

```text
CODEX_FINISH_REPORT_START
```

и:

```text
CODEX_FINISH_REPORT_END
```

Внутри блока уже есть nested `CHATGPT_HANDOFF_START` /
`CHATGPT_HANDOFF_END`, если repo handoff helper прошёл успешно.

## 6. Что делать при failure

Если какая-либо проверка показывает `fail`, посмотреть раздел `Failures`.
Script печатает только короткий excerpt, а не полный лог.

После исправления причины failure нужно снова запустить тот же mode. Не делать
commit/push, пока релевантные проверки не прошли.

## 7. Что script не делает и не должен делать

Script не должен:

- менять файлы;
- делать commit;
- делать push;
- читать содержимое клиентских файлов;
- читать `.xls`, `.xlsx` или generated `.csv`;
- печатать commercial data;
- печатать tokens/secrets/credentials;
- запускать quote smoke без explicit `--include-quote-smoke`;
- запускать quote generation напрямую;
- запускать low-level launcher;
- отправлять данные наружу сам по себе.

Он только запускает локальные read-only проверки и repo handoff helper. Quote
smoke является опциональным synthetic-only smoke и запускается только при
явном флаге.

## 8. Запрещённые файлы

Не добавлять и не передавать через finish report:

- `.xls`;
- `.xlsx`;
- generated `.csv`;
- screenshots;
- client files;
- temp files;
- tokens/secrets/credentials.

## 9. Почему это уменьшает копипаст Игоря

Одна команда собирает статусы проверок, короткие failure excerpts и готовый repo
handoff block. После этого Игорю не нужно вручную копировать выводы из `pytest`,
`mypy`, `ruff`, `black`, `git status` и GitHub Actions в отдельный статус для
ChatGPT.

# invoice_quote_filler v0.2.1: repo handoff runbook

## 1. Назначение helper

`scripts/build_repo_handoff.py` собирает компактный read-only handoff/status
packet по repo и печатает его в stdout.

Helper нужен, чтобы после задач Codex мог передать ChatGPT готовый текстовый
статус без скриншотов и ручного пересказа. Он собирает только repo
metadata/status и не читает содержимое рабочих, клиентских или generated файлов.

## 2. Когда запускать

Запускать helper можно после завершения задачи, перед передачей статуса в
ChatGPT или перед ручной проверкой GitHub Actions.

Если нужно полностью пропустить попытку read-only запроса к GitHub CLI, запускать
с `--no-ci`.

## 3. Команда запуска

```powershell
.\.venv\Scripts\python.exe .\scripts\build_repo_handoff.py
```

Без проверки CI через `gh`:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_repo_handoff.py --no-ci
```

## 4. Что означает clean/dirty

`clean` означает, что `git status --short --untracked-files=all` не вернул
изменённых или untracked файлов.

`dirty` означает, что в repo есть изменённые или untracked файлы. В этом случае
handoff block показывает только short status lines, без чтения содержимого
файлов.

## 5. Что означает CI success/failure/unknown

- `success` означает, что последний найденный GitHub Actions run для текущего
  HEAD завершился успешно.
- `failure` означает, что последний найденный run завершился ошибкой,
  отменой или timeout.
- `in_progress` означает, что run ещё выполняется или ожидает запуска.
- `unknown` означает, что `gh` недоступен, не авторизован, вернул ошибку,
  не нашёл run для HEAD или запуск выполнен с `--no-ci`.

Helper не требует `gh` для работы.

## 6. Что отправлять ChatGPT

Отправлять весь блок между:

```text
CHATGPT_HANDOFF_START
```

и:

```text
CHATGPT_HANDOFF_END
```

Не нужно прикладывать screenshots, `.xls`, `.xlsx`, generated `.csv` или
клиентские файлы.

## 7. Quote workflow block

`CHATGPT_HANDOFF` также содержит статический safe block `Quote workflow`.

Он нужен, чтобы в finish report сразу было видно:

- canonical launcher: `scripts/make_quote_capacity100_checked.ps1`;
- operator run card:
  `docs/invoice_quote_filler_v0_2_1_operator_run_card.md`;
- canonical smoke: `scripts/smoke_checked_quote_launcher.ps1`;
- manual stop перед клиентом;
- generated `.xlsx` является только internal draft.

Этот block не запускает generation, не запускает smoke, не читает КП и не
печатает client paths или commercial data. Он не является commercial approval.
STOP перед клиентом сохраняется: manual Igor check и отдельное Human Approval
required before sending to client.

## 8. Что делать при CI failure

Если `CI: failure`, открыть ссылку из `GitHub Actions` и посмотреть failing job.
В ChatGPT передавать handoff block и краткий текст ошибки из Actions logs.

Не добавлять в repo клиентские файлы или generated artifacts для диагностики.

## 9. Что helper не делает и не должен делать

Helper не должен:

- читать содержимое клиентских файлов;
- читать `.xls`, `.xlsx` или generated `.csv`;
- печатать commercial data;
- менять файлы;
- делать commit;
- делать push;
- запускать tests автоматически;
- запускать quote generation;
- запускать smoke helper;
- отправлять данные наружу сам по себе.

Он выполняет только read-only Git-команды и, если доступен `gh`, read-only
запрос к GitHub Actions.

## 10. Запрещённые файлы

Не добавлять и не передавать через helper:

- `.xls`;
- `.xlsx`;
- generated `.csv`;
- screenshots;
- client files;
- temp files.

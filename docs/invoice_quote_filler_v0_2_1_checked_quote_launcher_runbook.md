# invoice_quote_filler v0.2.1: checked quote launcher runbook

## 1. Назначение checked launcher

`scripts/make_quote_capacity100_checked.ps1` — безопасный wrapper перед
созданием черновика КП. Он сначала запускает
`scripts/preflight_quote_input.py`, печатает полный
`QUOTE_INPUT_PREFLIGHT_REPORT` и только после допустимого preflight запускает
существующий `scripts/make_quote_capacity100.ps1`.

Это canonical operator path для strict CSV -> draft КП.

Главная цель — уменьшить ручной копипаст и не дать случайно создать КП из CSV,
который preflight считает небезопасным.

## 2. Почему это отдельный wrapper

Existing launcher `scripts/make_quote_capacity100.ps1` не заменяется и не
изменяется. Он остаётся low-level/internal инструментом генерации и не является
основным операторским путём. Использовать его можно только если Игорь явно
решил обойти checked workflow.

Checked launcher добавляет защитный слой:

- проверяет input CSV через preflight;
- проверяет draft output path через `--draft-output`;
- блокирует генерацию при `FAIL`;
- блокирует генерацию при `WARN` без явного `-AllowWarn`;
- после successful generation запускает draft inspection;
- передаёт совместимые параметры в existing launcher.

Checked workflow:

```text
preflight -> generation -> draft inspection -> checked quote run report
```

## 3. Canonical команда запуска

```powershell
.\scripts\make_quote_capacity100_checked.ps1 "C:\Users\IgorN\Downloads\items.csv" "C:\Users\IgorN\Downloads\Черновик_КП.xlsx"
```

`ItemsCsv` и `Output` обязательны. Оба пути должны быть outside Git. Output
`.xlsx` не должен существовать до запуска.

## 4. Optional `-AllowWarn`

По умолчанию `WARN` не запускает генерацию. Это сделано специально: warning
означает, что нужна ручная проверка Игоря.

Если предупреждения проверены и приняты, можно повторить запуск:

```powershell
.\scripts\make_quote_capacity100_checked.ps1 "C:\Users\IgorN\Downloads\items.csv" "C:\Users\IgorN\Downloads\Черновик_КП.xlsx" -AllowWarn
```

`-AllowWarn` разрешает запуск generator только при `WARN`. При `FAIL` генерация
всё равно запрещена.

## 5. Pass-through параметров

Wrapper принимает совместимые параметры low-level/internal launcher:

- `Template`;
- `TemplateCapacity`;
- `Python`.

Если `Python` не передан, wrapper использует:

```text
<ProjectRoot>\.venv\Scripts\python.exe
```

Этот же Python используется для preflight, draft inspection и передаётся дальше
в `make_quote_capacity100.ps1`.

Пример:

```powershell
.\scripts\make_quote_capacity100_checked.ps1 `
  "C:\Users\IgorN\Downloads\items.csv" `
  "C:\Users\IgorN\Downloads\Черновик_КП.xlsx" `
  -Template "C:\Users\IgorN\Downloads\custom_template.xlsx" `
  -TemplateCapacity 100 `
  -Python ".\.venv\Scripts\python.exe"
```

## 6. Что происходит при PASS

При `PASS` wrapper запускает low-level/internal launcher:

```powershell
.\scripts\make_quote_capacity100.ps1 "<ItemsCsv>" "<Output>"
```

После генерации wrapper проверяет exit code generator и наличие output `.xlsx`.
Если output создан, wrapper запускает:

```powershell
.\.venv\Scripts\python.exe .\scripts\inspect_quote_draft.py --input "<Output>"
```

Wrapper печатает полный `QUOTE_DRAFT_INSPECTION_REPORT`, затем печатает
`CHECKED_QUOTE_RUN_REPORT`.

## 7. Что происходит при WARN

При `WARN` без `-AllowWarn` wrapper:

- не запускает generator;
- печатает `Generation: skipped`;
- печатает `Inspection: skipped`;
- сообщает, что нужна ручная проверка Игоря и повторный запуск с `-AllowWarn`;
- завершается с non-zero exit code.

При `WARN` с `-AllowWarn` wrapper может запустить generator, но ручная проверка
созданного draft всё равно обязательна.

## 8. Что происходит при FAIL

При `FAIL` wrapper:

- не запускает generator;
- печатает `Generation: skipped`;
- печатает `Inspection: skipped`;
- завершается с non-zero exit code.

CSV нужно исправить или пересоздать, затем снова запустить checked launcher.

## 9. Что означает `Inspection`

`Inspection: pass` означает, что generated `.xlsx`:

- существует;
- находится outside Git;
- не пустой;
- открывается через `openpyxl`;
- содержит минимум один worksheet.

`Inspection: fail` означает, что draft inspection не прошёл. Такой draft нельзя
использовать. Нужно прочитать `QUOTE_DRAFT_INSPECTION_REPORT`, устранить причину
и создать draft заново безопасным способом.

`Inspection: skipped` означает, что inspection не запускался, потому что
preflight заблокировал генерацию или generation failed.

Inspection не читает и не печатает cell values. Даже `Inspection: pass` не
означает, что КП можно отправлять клиенту. Technical PASS, `Inspection: pass`
или smoke PASS не являются commercial approval.

## 10. Статус generated `.xlsx`

Generated `.xlsx` — только internal draft. Его нельзя считать готовым КП.

Перед отправкой клиенту обязательна ручная проверка Игоря:

- состава позиций;
- количества;
- текста приборов и шкафов;
- реквизитов и шаблонных областей;
- итогового `.xlsx` после генерации.

Для отправки клиенту требуется отдельное Human Approval. Нельзя запускать
закупку, цех, shipment или отправку клиенту только на основании technical PASS.

## 11. Что wrapper не делает

Wrapper не должен:

- отправлять КП клиенту;
- считать technical PASS коммерческим approval;
- запускать закупку/цех/отправку без решения Игоря;
- делать commit/push;
- менять source CSV;
- менять template;
- менять existing launcher;
- обходить preflight;
- запускать generator при `FAIL`;
- запускать generator при `WARN` без `-AllowWarn`;
- перезаписывать existing output `.xlsx`;
- создавать файлы inside Git.
- читать или печатать cell values.

## 12. Запрещённые файлы

Не добавлять в repo и не прикладывать к отчёту:

- `.xls`;
- `.xlsx`;
- generated `.csv`;
- screenshots;
- client files;
- temp files;
- tokens/secrets/credentials.

## 13. Итоговый report

После каждого запуска wrapper печатает:

```text
CHECKED_QUOTE_RUN_REPORT_START

Input:
<path>

Output:
<path>

Preflight:
PASS / WARN / FAIL

Generation:
pass / fail / skipped

Inspection:
pass / fail / skipped

Output exists:
yes / no

Next:
manual Igor check required before sending to client

CHECKED_QUOTE_RUN_REPORT_END
```

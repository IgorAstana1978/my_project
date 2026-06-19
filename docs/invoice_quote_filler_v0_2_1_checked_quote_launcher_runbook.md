# invoice_quote_filler v0.2.1: checked quote launcher runbook

## 1. Назначение checked launcher

`scripts/make_quote_capacity100_checked.ps1` — безопасный wrapper перед
созданием черновика КП. Он сначала запускает
`scripts/preflight_quote_input.py`, печатает полный
`QUOTE_INPUT_PREFLIGHT_REPORT` и только после допустимого preflight запускает
существующий `scripts/make_quote_capacity100.ps1`.

Главная цель — уменьшить ручной копипаст и не дать случайно создать КП из CSV,
который preflight считает небезопасным.

## 2. Почему это отдельный wrapper

Existing launcher `scripts/make_quote_capacity100.ps1` не заменяется и не
изменяется. Он остаётся низкоуровневым инструментом генерации.

Checked launcher добавляет защитный слой:

- проверяет input CSV через preflight;
- проверяет draft output path через `--draft-output`;
- блокирует генерацию при `FAIL`;
- блокирует генерацию при `WARN` без явного `-AllowWarn`;
- передаёт совместимые параметры в existing launcher.

## 3. Команда запуска

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

Wrapper принимает совместимые параметры existing launcher:

- `Template`;
- `TemplateCapacity`;
- `Python`.

Если `Python` не передан, wrapper использует:

```text
<ProjectRoot>\.venv\Scripts\python.exe
```

Этот же Python используется для preflight и передаётся дальше в
`make_quote_capacity100.ps1`.

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

При `PASS` wrapper запускает existing launcher:

```powershell
.\scripts\make_quote_capacity100.ps1 "<ItemsCsv>" "<Output>"
```

После генерации wrapper проверяет exit code generator и наличие output `.xlsx`.
Затем печатает `CHECKED_QUOTE_RUN_REPORT`.

## 7. Что происходит при WARN

При `WARN` без `-AllowWarn` wrapper:

- не запускает generator;
- печатает `Generation: skipped`;
- сообщает, что нужна ручная проверка Игоря и повторный запуск с `-AllowWarn`;
- завершается с non-zero exit code.

При `WARN` с `-AllowWarn` wrapper может запустить generator, но ручная проверка
созданного draft всё равно обязательна.

## 8. Что происходит при FAIL

При `FAIL` wrapper:

- не запускает generator;
- печатает `Generation: skipped`;
- завершается с non-zero exit code.

CSV нужно исправить или пересоздать, затем снова запустить checked launcher.

## 9. Статус generated `.xlsx`

Generated `.xlsx` — только internal draft. Его нельзя считать готовым КП.

Перед отправкой клиенту обязательна ручная проверка Игоря:

- состава позиций;
- количества;
- текста приборов и шкафов;
- реквизитов и шаблонных областей;
- итогового `.xlsx` после генерации.

## 10. Что wrapper не делает

Wrapper не должен:

- отправлять КП клиенту;
- делать commit/push;
- менять source CSV;
- менять template;
- менять existing launcher;
- обходить preflight;
- запускать generator при `FAIL`;
- запускать generator при `WARN` без `-AllowWarn`;
- перезаписывать existing output `.xlsx`;
- создавать файлы inside Git.

## 11. Запрещённые файлы

Не добавлять в repo и не прикладывать к отчёту:

- `.xls`;
- `.xlsx`;
- generated `.csv`;
- screenshots;
- client files;
- temp files;
- tokens/secrets/credentials.

## 12. Итоговый report

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

Output exists:
yes / no

Next:
manual Igor check required before sending to client

CHECKED_QUOTE_RUN_REPORT_END
```

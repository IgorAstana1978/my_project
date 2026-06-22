# invoice_quote_filler v0.2.1: quote draft inspection runbook

## 1. Назначение helper

`scripts/inspect_quote_draft.py` проверяет generated draft `.xlsx` после
создания КП и печатает safe metadata report без содержимого workbook.

Helper нужен как быстрый read-only sanity check перед ручной проверкой Игоря:
файл существует, находится outside Git, не пустой, открывается через `openpyxl`
и содержит хотя бы один worksheet.

## 2. Когда запускать

Запускать после создания draft `.xlsx`, например после checked launcher или
ручного generation flow, но до отправки клиенту.

Этот helper не заменяет ручную проверку Игоря. Он только подтверждает, что файл
похож на читаемый workbook.

## 3. Команда запуска

```powershell
.\.venv\Scripts\python.exe .\scripts\inspect_quote_draft.py --input "C:\Users\IgorN\Downloads\Черновик_КП.xlsx"
```

Input должен быть `.xlsx` outside Git.

## 4. Что проверяет

Helper проверяет:

- input path exists;
- suffix `.xlsx`;
- файл находится outside Git project;
- file size больше нуля;
- workbook открывается через `openpyxl`;
- workbook содержит минимум один worksheet.

## 5. Что печатает

Report содержит только safe metadata:

- absolute input path;
- PASS/FAIL status;
- check statuses;
- worksheet count;
- file size bytes;
- короткие failure messages без cell contents.

Helper не печатает:

- sheet names;
- cell values;
- formulas;
- commercial data;
- tokens/secrets/credentials.

## 6. Exit code

- `PASS` возвращает exit code `0`;
- `FAIL` возвращает exit code `1`.

## 7. Что делать при FAIL

Прочитать `Failures` и исправить причину:

- missing file;
- wrong suffix;
- input inside Git;
- zero-byte file;
- corrupt/unreadable workbook;
- workbook without worksheets.

После исправления снова запустить helper. Не отправлять КП клиенту, пока draft не
прошёл inspection и ручную проверку Игоря.

## 8. Что helper не делает

Helper не должен:

- менять `.xlsx`;
- создавать новый `.xlsx`;
- читать или печатать cell contents;
- печатать commercial data;
- отправлять КП клиенту;
- делать commit/push;
- менять source scripts;
- менять template.

## 9. Запрещённые файлы

Не добавлять в repo и не прикладывать к отчёту:

- `.xls`;
- `.xlsx`;
- generated `.csv`;
- screenshots;
- client files;
- temp files;
- tokens/secrets/credentials.

## 10. Report format

```text
QUOTE_DRAFT_INSPECTION_REPORT_START

Input:
<path>

Status:
PASS / FAIL

Checks:
input path: pass/fail
outside Git: pass/fail
suffix: pass/fail
file size: pass/fail
workbook opens: pass/fail
worksheets present: pass/fail

Workbook:
worksheet count: <N>
file size bytes: <N>

Warnings:
none

Failures:
none / short failures without cell contents

Next:
manual Igor check required before sending to client

QUOTE_DRAFT_INSPECTION_REPORT_END
```

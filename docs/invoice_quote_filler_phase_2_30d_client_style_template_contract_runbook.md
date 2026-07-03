# Phase 2.30d: client-style invoice template contract preflight

## Назначение

`scripts/preflight_client_style_invoice_template_contract.py` выполняет
read-only fail-closed проверку XLSX-шаблона и его machine-readable contract
перед будущим client-style invoice export.

Эта фаза не реализует exporter, не создаёт новый счёт и не создаёт
client-ready XLSX. Успешный `PASS` подтверждает только техническое соответствие
шаблона contract.

## Входы

Скрипт принимает два обязательных аргумента:

```text
--template-xlsx
--contract-json
```

Production template всегда должен находиться outside Git. Production contract
также должен находиться outside Git. Внутри Git разрешён только документирующий
placeholder-файл:

```text
examples/client_style_invoice_template_contract.example.json
```

Этот example предназначен для документации и тестов. Его placeholder SHA256
не является approval реального шаблона.

## Contract JSON

Contract фиксирует:

- идентификатор, имя и версию contract/template;
- ожидаемое имя рабочего листа;
- SHA256 утверждённого template;
- явно разрешённые дополнительные листы;
- orientation, paper size и обязательность print area;
- ячейки invoice number/date, payer, object, amount words и signer;
- строки table header и первой позиции;
- колонки таблицы;
- fixed labels, проверяемые substring match.

`object_cell` может быть строкой с Excel coordinate либо `null`.
`print.orientation` и `print.paper_size` могут быть строкой либо `null`; при
`null` соответствующая настройка не сравнивается. Для A4 используется Excel
paper size code `"9"`.

SHA256 должен содержать ровно 64 lowercase hex characters. Любое изменение
template аннулирует contract до выпуска нового contract с новым hash.

## Fail-Closed Проверки

Preflight проверяет:

- существование, suffix и outside-Git policy входов;
- JSON root и обязательную schema;
- типы и непустые значения полей;
- формат и совпадение SHA256;
- наличие expected worksheet;
- отсутствие неразрешённых дополнительных sheets;
- Excel cell coordinates и columns;
- порядок `table_header_row < first_item_row`;
- нахождение всех layout coordinates в used range листа;
- fixed labels без вывода полного ожидаемого или фактического текста;
- orientation и paper size, если они заданы;
- наличие print area, если она обязательна;
- неизменность SHA256 template после проверки.

Скрипт открывает workbook только read-only и не сохраняет его.

## Запуск

Из корня репозитория:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\preflight_client_style_invoice_template_contract.py `
  --template-xlsx "C:\outside-git\approved-client-template.xlsx" `
  --contract-json "C:\outside-git\approved-template-contract.json"
```

Отчёт печатается между маркерами:

```text
CLIENT_STYLE_TEMPLATE_CONTRACT_PREFLIGHT_REPORT_START
CLIENT_STYLE_TEMPLATE_CONTRACT_PREFLIGHT_REPORT_END
```

Exit code `0` возвращается только при `PASS`; при любом fail-closed red flag
возвращается `1`.

## Safety Boundaries

- preflight не изменяет и не сохраняет template;
- preflight не создаёт output XLSX;
- preflight не подключён к writer, launcher или calculator;
- никаких blind guesses, autofill или default client terms нет;
- отчёт не печатает клиентские реквизиты или длинные fixed labels;
- `PASS` не является approval на client-style export;
- `PASS` не является разрешением генерировать или отправлять счёт клиенту;
- перед генерацией или отправкой требуется отдельное Human Approval.

## Проверка Разработчиком

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov `
  tests/test_preflight_client_style_invoice_template_contract.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m black --check .
git diff --check
.\scripts\finish_quote_workflow.ps1
```

Generated test XLSX разрешены только внутри pytest `tmp_path` и не должны
попадать в Git.

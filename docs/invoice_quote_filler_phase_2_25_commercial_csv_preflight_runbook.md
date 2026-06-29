# invoice_quote_filler Phase 2.25: commercial CSV preflight

## 1. Статус и границы фазы

Phase 2.25 добавляет отдельный commercial CSV contract для будущей подготовки
внутреннего черновика КП с ценами.

В этой фазе:

- можно создать пустой commercial CSV template outside Git;
- можно выполнить read-only preflight заполненного commercial CSV;
- нельзя создавать `.xlsx`;
- нельзя записывать цены в Excel;
- нельзя считать preflight PASS коммерческим или клиентским approval;
- нельзя автоматически отправлять данные клиенту или запускать
  purchase/workshop/shipment.

Существующий strict 5-column technical workflow остаётся отдельным и продолжает
запрещать commercial columns.

## 2. Точный CSV contract

CSV должен быть UTF-8 или UTF-8 with BOM, использовать разделитель `;` и иметь
ровно следующий header:

```text
name;unit;quantity;instruments_and_devices;cabinet_type_dimensions_material;unit_price_kzt;price_includes_vat;price_confirmed_by_igor
```

Все восемь колонок обязательны. Unknown, extra, missing, duplicate или
переставленные колонки запрещены.

## 3. Создание пустого template

Запускать из repo root:

```powershell
.\scripts\create_quote_commercial_csv_template.ps1 "C:\Users\IgorN\Downloads\commercial_items.csv"
```

Команда:

- создаёт только header без item rows;
- требует новый `.csv` path outside Git;
- не создаёт отсутствующий parent directory;
- не перезаписывает существующий файл;
- не создаёт КП и не запускает preflight.

Template и заполненные commercial CSV нельзя добавлять в Git.

## 4. Read-only preflight

Команда:

```powershell
.\.venv\Scripts\python.exe .\scripts\preflight_quote_commercial_input.py `
  --input "C:\Users\IgorN\Downloads\commercial_items.csv"
```

Preflight читает CSV и печатает только безопасный отчёт. Он не изменяет input,
не создаёт CSV/XLSX и не печатает полные строки или значения цен.

## 5. Fail-closed правила

- input должен быть существующим `.csv` outside Git;
- row count должен быть `1-100`;
- `name`, `unit`, `quantity`, `instruments_and_devices` и
  `cabinet_type_dimensions_material` обязательны;
- `quantity` должен быть положительным целым числом без decimal form;
- `unit_price_kzt` должен быть положительным целым числом;
- decimal, comma, exponent, leading/trailing/internal spaces в цене запрещены;
- `price_includes_vat` должен быть точным lowercase `yes` или `no`;
- VAT mode должен быть одинаковым во всех строках;
- `price_confirmed_by_igor` должен быть точным lowercase `yes`;
- client-ready/send/approval flags и любые другие колонки запрещены.

Любое нарушение даёт `FAIL` и non-zero exit code.

## 6. Значение PASS

`PASS` означает только то, что commercial input прошёл автоматические
технические проверки и может использоваться для будущей подготовки внутреннего
draft.

В Phase 2.25 XLSX generation не реализован. Даже после будущей генерации
обязательны:

- manual Igor check;
- отдельное Human Approval перед любым client-ready use;
- отдельное решение перед отправкой клиенту.

Technical PASS не подтверждает финальную цену, итог, VAT, условия оплаты,
комплектацию или готовность документа для клиента.

## 7. Безопасность файлов

Запрещено добавлять в Git:

- generated или заполненные `.csv`;
- `.xls` и `.xlsx`;
- client files;
- screenshots;
- temporary files;
- tokens, secrets и credentials.

Template/preflight helpers не выполняют `git add`, commit, push, отправку
клиенту или производственные действия.

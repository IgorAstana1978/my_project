# invoice_quote_filler v0.2.1: legacy XLS extractor runbook

## 1. Назначение

Extractor нужен только для безопасного преобразования legacy `.xls` в strict CSV
для текущего runtime.

Он не создаёт КП напрямую и не переносит цены, суммы или любые commercial data.
CSV после extractor является только промежуточным файлом для ручной проверки.

## 2. Текущий стабильный статус

- Phase 1 реализована.
- Dependency: `xlrd>=2.0,<3`.
- CI зелёный на `b02d46f test: fix legacy xls extractor mypy typing`.
- Ручной synthetic `.xls` smoke пройден outside Git.

## 3. Безопасный рабочий порядок

- Source `.xls` должен оставаться outside Git.
- Output `.csv` должен оставаться outside Git.
- Generated `.xlsx` должен оставаться outside Git.
- Клиентские файлы не должны попадать в repo.

Не добавлять в Git `.xls`, `.xlsx`, generated `.csv`, screenshots, client
files или temp files.

## 4. Команда: extract `.xls` to strict CSV

```powershell
.\.venv\Scripts\python.exe .\scripts\extract_legacy_xls_items_to_csv.py `
  --input "C:\Users\IgorN\Downloads\legacy_invoice.xls" `
  --output "C:\Users\IgorN\Downloads\items_from_legacy.csv"
```

## 5. Ожидаемый формат CSV

Output CSV должен содержать только:

```text
name;unit;quantity;instruments_and_devices;cabinet_type_dimensions_material
```

## 6. Что extractor игнорирует

Extractor игнорирует и не должен экспортировать:

- цены;
- суммы;
- `ИТОГО`;
- `всего прописью`;
- НДС/VAT;
- валюты;
- условия оплаты;
- условия поставки;
- банковские реквизиты;
- notes/comments;
- любые commercial data.

## 7. Ручная проверка перед созданием КП

Игорь должен вручную открыть generated CSV и проверить:

- есть только 5 strict columns;
- наименования позиций корректные;
- единицы измерения корректные;
- quantity является integer;
- нет prices/sums/VAT/payment/bank/commercial data;
- row count находится в диапазоне 1-100;
- нет shifted rows.

## 8. Следующая команда после ручной проверки CSV

Canonical operator path после ручной проверки CSV:

```powershell
.\scripts\make_quote_capacity100_checked.ps1 "C:\Users\IgorN\Downloads\items_from_legacy.csv" "C:\Users\IgorN\Downloads\Черновик_КП.xlsx"
```

Checked workflow выполняет:

```text
preflight -> generation -> draft inspection -> checked quote run report
```

Прямой `make_quote_capacity100.ps1` является low-level/internal launcher и не
является основным операторским путём. Использовать его можно только если Игорь
явно решил обойти checked workflow.

## 9. Статус выходного `.xlsx`

Generated `.xlsx` является только внутренним draft.

Он не предназначен для отправки клиенту и требует ручной проверки Игоря. Prices,
sums, VAT, terms, dates и commercial decisions не утверждаются extractor.
Technical PASS, `Inspection: pass` или smoke PASS не являются commercial
approval. Перед отправкой клиенту обязательны manual Igor check и отдельное
Human Approval.

## 10. Fail-closed поведение

Extractor должен завершаться ошибкой при:

- missing headers;
- no rows;
- более 100 rows;
- non-integer quantity;
- shifted/ambiguous layout;
- multiple plausible item tables;
- output exists;
- output inside Git;
- input not `.xls`;
- missing paths.

## 11. Диагностика типовых ошибок

- `output CSV already exists` -> выбрать новое имя output или удалить старый
  файл вручную после проверки.
- `output CSV must be outside the Git project` -> сохранить в Downloads/Desktop,
  а не в repo.
- `missing required headers` -> layout файла не поддерживается.
- `quantity must be an integer` -> исправить source или собрать CSV вручную.
- `multiple plausible item tables` -> extractor безопасно отказался от
  ambiguous file.

## 12. Definition of Done / критерии готовности

- Docs добавлены/обновлены только в allowed scope.
- Generated/client files отсутствуют.
- `git diff --check` passed.
- Optional targeted tests всё ещё проходят.
- Status clean после commit/push только при отдельном approval.

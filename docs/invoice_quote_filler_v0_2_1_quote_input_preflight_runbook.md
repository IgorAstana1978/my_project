# invoice_quote_filler v0.2.1: quote input preflight runbook

## 1. Назначение preflight helper

`scripts/preflight_quote_input.py` проверяет strict CSV перед запуском
canonical checked launcher `make_quote_capacity100_checked.ps1` и печатает
безопасный отчёт для Игоря и ChatGPT.

Helper не создаёт КП и не изменяет входной CSV. Он только проверяет структуру,
row count, обязательные поля, quantity и очевидные commercial tokens.

## 2. Когда запускать

Запускать после подготовки strict CSV и до создания черновика КП.

Особенно полезно запускать после:

- ручной сборки CSV;
- extraction legacy `.xls -> strict CSV`;
- правки CSV после ручной проверки.

## 3. Команда запуска

```powershell
.\.venv\Scripts\python.exe .\scripts\preflight_quote_input.py --input "C:\Users\IgorN\Downloads\items.csv"
```

С подсказкой следующей команды:

```powershell
.\.venv\Scripts\python.exe .\scripts\preflight_quote_input.py `
  --input "C:\Users\IgorN\Downloads\items.csv" `
  --draft-output "C:\Users\IgorN\Downloads\Черновик_КП.xlsx"
```

`--draft-output` не создаёт `.xlsx`. Он только включает проверку пути и
показывает рекомендуемую следующую команду.

## 4. Что проверяет

Helper проверяет:

- input path exists;
- suffix `.csv`;
- input находится outside Git;
- header exactly equals strict 5-column header;
- нет extra/missing columns;
- row count находится в диапазоне 1-100;
- `quantity` является integer;
- `name`, `unit`, `quantity` не пустые;
- obvious commercial columns/tokens отсутствуют.
- если передан `--draft-output`, draft `.xlsx` находится outside Git, имеет
  suffix `.xlsx`, parent directory существует, файл ещё не существует, и путь не
  совпадает с input CSV.

Strict columns:

```text
name
unit
quantity
instruments_and_devices
cabinet_type_dimensions_material
```

## 5. Что означает PASS/WARN/FAIL

- `PASS` означает, что автоматические preflight checks прошли.
- `WARN` означает, что критических ошибок нет, но есть замечания, например
  пустые optional text columns.
- `FAIL` означает, что запускать checked workflow небезопасно до исправления
  CSV.

Manual Igor check всё равно required при любом статусе.

## 6. Что делать при FAIL

Прочитать раздел `Failures`. Helper показывает row number, column name и issue
type, но не печатает полные строки CSV.

Исправить source CSV вручную или пересоздать его безопасным способом. После
исправления снова запустить preflight.

## 7. Что делать при WARN

Проверить раздел `Warnings`. Если предупреждения ожидаемы, например optional
columns пустые в коротком сценарии, можно продолжать после ручной проверки
Игоря.

## 8. Следующая команда `make_quote_capacity100_checked.ps1`

После `PASS` или принятого `WARN` можно запускать:

```powershell
.\scripts\make_quote_capacity100_checked.ps1 "C:\Users\IgorN\Downloads\items.csv" "C:\Users\IgorN\Downloads\Черновик_КП.xlsx"
```

Checked workflow выполняет:

```text
preflight -> generation -> draft inspection -> checked quote run report
```

Прямой `make_quote_capacity100.ps1` является low-level/internal launcher и не
является основным операторским путём. Использовать его можно только если Игорь
явно решил обойти checked workflow.

Generated `.xlsx` остаётся внутренним draft и требует ручной проверки Игоря.
Technical PASS, `Inspection: pass` или smoke PASS не являются commercial
approval. Перед отправкой клиенту обязательны manual Igor check и отдельное
Human Approval.
Preflight fail-closed, если draft output exists, находится inside Git, имеет
wrong suffix, missing parent или совпадает с input CSV.

## 9. Что helper не делает

Helper не должен:

- создавать КП;
- запускать checked launcher или low-level launcher;
- создавать output `.xlsx`;
- создавать generated `.csv`;
- менять файлы;
- делать commit/push;
- читать `.xls` или `.xlsx`;
- печатать commercial data;
- печатать полные строки CSV при ошибках.

## 10. Запрещённые файлы

Не добавлять в repo и не прикладывать к отчёту:

- `.xls`;
- `.xlsx`;
- generated `.csv`;
- screenshots;
- client files;
- temp files;
- tokens/secrets/credentials.

## 11. Почему это уменьшает ручную проверку Игоря

Одна команда показывает, можно ли безопасно переходить к созданию черновика КП,
какие поля нужно проверить вручную и почему запуск может быть небезопасен. Это
снижает ручной копипаст и помогает не пропустить commercial data в strict CSV.

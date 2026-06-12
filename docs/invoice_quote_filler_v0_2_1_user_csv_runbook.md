# invoice_quote_filler v0.2.1: запуск КП из CSV

Короткая инструкция для Игоря: как из CSV получить внутренний черновик КП.

## 1. Взять sample CSV

Формат можно взять из безопасного sample-файла:

```text
examples/invoice_quote_items_capacity100_sample.csv
```

CSV должен быть UTF-8 или UTF-8 with BOM. Разделитель: `;`.

Заполнять нужно ровно 5 колонок:

```text
name
unit
quantity
instruments_and_devices
cabinet_type_dimensions_material
```

Правила:

- `quantity` должен быть целым числом.
- Текстовые поля могут содержать русский текст.
- Поля в кавычках могут содержать `;` или переносы строк.
- Коммерческие колонки добавлять нельзя.
- Нельзя добавлять `price`, `price_kzt`, `sum`, `vat`, `currency`, `term`, `discount`, `price_confirmed_by_igor`.

## 2. Использовать tuned_v3 template

Рабочий capacity100 template лежит outside Git:

```text
C:\Users\IgorN\Downloads\Фирменный_шаблон_счёта-КП_v0.3_capacity100_tuned_v3_ДиН_ВА-КЭС.xlsx
```

Этот template нельзя перезаписывать.

## 3. Запустить из PowerShell

Output нужно сохранять outside Git. Файл output не должен существовать до запуска.

Пример:

```powershell
.\.venv\Scripts\python.exe scripts\run_invoice_quote_extended_from_csv.py --items-csv examples\invoice_quote_items_capacity100_sample.csv --template "C:\Users\IgorN\Downloads\Фирменный_шаблон_счёта-КП_v0.3_capacity100_tuned_v3_ДиН_ВА-КЭС.xlsx" --template-capacity 100 --output "C:\Users\IgorN\Downloads\Тест_capacity100_sample_csv_draft.xlsx"
```

Скрипт должен вывести `CREATED:` и путь к созданному файлу.

## 4. Проверить черновик

Сгенерированный `.xlsx` является только внутренним черновиком.

Перед отправкой клиенту Игорь вручную проверяет:

- наименования, единицы, количества и комплектацию;
- переносы строк и визуальный layout;
- цены, сроки, итоги, НДС и любые коммерческие данные;
- финальную формулировку и вложения для клиента.

Сгенерированные `.xlsx` файлы нельзя добавлять в Git.

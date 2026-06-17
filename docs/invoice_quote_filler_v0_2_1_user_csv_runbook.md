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

Основной пользовательский путь - короткий Windows launcher. Запускать из repo root:

```text
C:\Users\IgorN\projects\my_project
```

На вход можно дать обычный strict items CSV, даже если в длинных descriptions есть ручные переносы. Launcher сам использует default tuned_v3 template из Downloads, default capacity `100`, вызывает one-command compact CSV runner и передаёт результат в рабочую CSV runtime chain. Temporary compact CSV вручную сохранять не нужно.

Пример:

```powershell
.\scripts\make_quote_capacity100.ps1 "C:\Users\IgorN\Downloads\items.csv" "C:\Users\IgorN\Downloads\Черновик_КП.xlsx"
```

Если PowerShell policy блокирует запуск `.ps1`, использовать:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\make_quote_capacity100.ps1 "C:\Users\IgorN\Downloads\items.csv" "C:\Users\IgorN\Downloads\Черновик_КП.xlsx"
```

Скрипт должен вывести понятное сообщение и путь к созданному файлу.

## 4. Проверить черновик

Сгенерированный `.xlsx` является только внутренним черновиком.

Перед отправкой клиенту Игорь вручную проверяет:

- наименования, единицы, количества и комплектацию;
- переносы строк и визуальный layout;
- цены, сроки, итоги, НДС и любые коммерческие данные;
- финальную формулировку и вложения для клиента.

Сгенерированные `.xlsx` файлы нельзя добавлять в Git.

## 5. Практическая заметка про compact CSV

Если старый счёт или CSV содержит много ручных переносов внутри длинных descriptions, one-command runner сам подготовит temporary compact CSV. Ручной compact CSV обычно нужен только для диагностики или визуального сравнения.

При compact CSV:

- не менять смысл позиции;
- не добавлять коммерческие данные;
- убрать лишние пустые строки и ручные переносы внутри длинных descriptions;
- сохранить только 5 разрешённых колонок.

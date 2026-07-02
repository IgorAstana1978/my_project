# Phase 2.29a: read-only price calculation draft

## Назначение

`scripts/calc_quote_price_draft.py` рассчитывает предварительную цену щита
только по заранее подтверждённому composition CSV.

Это отдельный read-only контур:

```text
confirmed composition CSV
    -> read-only lookup во вкладке КРН
    -> preliminary price draft report
    -> manual Igor check
    -> отдельное Human Approval
```

Скрипт не читает схемы, картинки или проекты, не создаёт XLSX КП, не меняет
прайсовую книгу и не подключён к technical или commercial writer/launcher.

## Входной CSV

CSV должен быть в UTF-8 и использовать разделитель `;`. Заголовок и его порядок
фиксированы:

```text
product_name;cabinet_code;consumables_factor;component_code;component_qty;install_type
```

Минимальный подтверждённый пример:

```text
product_name;cabinet_code;consumables_factor;component_code;component_qty;install_type
РУ-АВР / ЩРН-24;CAB-KRN-24;1.20;EKF-VA47-29-1P;4;modular_1p
РУ-АВР / ЩРН-24;CAB-KRN-24;1.20;EKF-VA47-29-3P;3;modular_3p
РУ-АВР / ЩРН-24;CAB-KRN-24;1.20;EKF-RN-47;1;modular_1p
```

Все строки одного запуска должны иметь одинаковые `product_name`,
`cabinet_code` и `consumables_factor`. Количество должно быть положительным
целым числом. `install_type` должен совпадать с встроенной подтверждённой картой
компонента.

## Разрешённый scope Phase 2.29a

Скрипт обращается только к вкладке `КРН`.

Встроенная карта компонентов:

| component_code | Строка в КРН | install_type |
|---|---|---|
| `EKF-VA47-29-1P` | `ВА47 1 полюсный` | `modular_1p` |
| `EKF-VA47-29-3P` | `ВА47 3 полюсный до 63А` | `modular_3p` |
| `EKF-RN-47` | `независимый расцепитель для ВА47 РН47` | `modular_1p` |

Встроенная карта шкафов:

| cabinet_code | Строка в КРН |
|---|---|
| `CAB-KRN-24` | `Корпус КРН-24 395х330х100` |

Для компонентов материал читается из колонки `B`, работа — из колонки `C`.
Шкаф читается только из правой таблицы `L:M`.

Вкладка `Прайс` запрещена: скрипт не выбирает и не перебирает её строки.
Старый файл `Таблица 05.01.2026.xlsx` использовать нельзя.

Если код, строка или цена отсутствуют, неоднозначны, являются формулой либо
не являются положительным целым числом, расчёт завершается `FAIL` с red flag.
Подбор похожей строки и угадывание цены запрещены.

## Формула

```text
component_material_total = sum(component material price * quantity)
work_total = sum(component work price * quantity)
base = cabinet_price + component_material_total * consumables_factor + work_total
total = round_half_up(base * 1.25 * 1.15)
```

Все входные цены уже включают НДС. НДС отдельно не рассчитывается.

Эталон Phase 2.29a:

```text
component_material_total = 16 900
work_total = 2 700
cabinet_price = 7 985
consumables_factor = 1.20
base = 30 965
total preliminary price = 44 512
```

## Запуск

Из корня репозитория:

```powershell
.\.venv\Scripts\python.exe .\scripts\calc_quote_price_draft.py `
  --price-workbook "C:\Users\IgorN\Downloads\Таблица 05.01.2026 верная.xlsx" `
  --input-csv "C:\Users\IgorN\Downloads\confirmed_composition.csv"
```

Команда только читает указанные файлы и печатает отчёт между маркерами
`PRICE_CALCULATION_DRAFT_REPORT_START` и
`PRICE_CALCULATION_DRAFT_REPORT_END`.

## Fail-closed границы

- `PASS` означает только успешный технический предварительный расчёт;
- `PASS` не является коммерческим одобрением;
- цена остаётся предварительной;
- перед переносом цены в commercial CSV требуется Igor approval;
- затем обязательны manual Igor check и отдельное Human Approval;
- скрипт не создаёт и не меняет XLSX КП;
- скрипт не меняет technical/commercial workflow;
- автоматической отправки клиенту нет;
- прайсовую книгу, composition CSV и generated artifacts нельзя добавлять в
  Git без отдельного подтверждения.

# Phase 2.28: commercial quote checked launcher

## Назначение

`make_quote_capacity100_commercial_checked.ps1` создаёт только внутренний
черновик commercial КП из заранее проверяемого восьмиколоночного CSV.

Launcher вызывает изолированный commercial writer, который выполняет
commercial preflight и reconciliation. Technical PASS не является коммерческим
одобрением или разрешением на отправку документа клиенту.

## Короткий запуск

Запускать из корня репозитория:

```powershell
.\scripts\make_quote_capacity100_commercial_checked.ps1 `
  "C:\Users\IgorN\Downloads\commercial_items.csv" `
  "C:\Users\IgorN\Downloads\commercial_internal_draft.xlsx"
```

Первые два позиционных параметра:

1. `CommercialCsv` — заполненный commercial CSV outside Git.
2. `Output` — новый XLSX path outside Git.

По умолчанию используется фирменный capacity100 template
`Фирменный_шаблон_счёта-КП_v0.4_capacity100_tuned_v4_ДиН_ВА-КЭС.xlsx` из
`$env:USERPROFILE\Downloads`. Launcher не ищет и не выбирает другие XLSX-файлы.

Если canonical template находится в другом месте, путь нужно передать явно:

```powershell
.\scripts\make_quote_capacity100_commercial_checked.ps1 `
  "C:\Users\IgorN\Downloads\commercial_items.csv" `
  "C:\Users\IgorN\Downloads\commercial_internal_draft.xlsx" `
  -Template "C:\Users\IgorN\Downloads\approved_capacity100_template.xlsx"
```

Опциональный `-Python` позволяет явно указать Python executable. Без параметра
используется `.\.venv\Scripts\python.exe`.

## Опциональные реквизиты КП

Параметр `-QuoteMetadataJson` принимает strict UTF-8 JSON следующего контракта:

```json
{
  "schema_version": "quote_metadata.v0.1",
  "document_number": "463",
  "document_date": "2026-07-10",
  "payer_name": "ТОО «Rich energy»",
  "payment_terms": "100% предоплата",
  "manufacturing_lead_time": "7–10 рабочих дней",
  "delivery_terms": "EXW, г. Астана",
  "vat_rate_percent": 16,
  "validity_period": null,
  "object_name": null,
  "basis_project": null,
  "item_notes": [
    {
      "item_number": 2,
      "text": "ВН 3Р 25А заменён на ВН 3Р 32А — номинал 25А отсутствует в линейке CHINT."
    }
  ]
}
```

```powershell
.\scripts\make_quote_capacity100_commercial_checked.ps1 `
  "C:\Users\IgorN\Downloads\commercial_items.csv" `
  "C:\Users\IgorN\Downloads\commercial_internal_draft.xlsx" `
  -QuoteMetadataJson "C:\Users\IgorN\Downloads\quote_metadata.json"
```

Все поля обязательны, если metadata передан; неизвестные поля, malformed JSON,
не-UTF-8 содержимое и неподдерживаемая версия схемы завершают запуск с FAIL.
`validity_period: null` очищает placeholder срока действия. Без metadata прежний
вызов остаётся совместимым и реквизиты шаблона не переписываются.

`object_name` и `basis_project` принимают непустую строку или `null`. Пустая или
whitespace-only строка завершают запуск с FAIL без output. Значение `null`
полностью очищает соответствующую строку шаблона; строка записывается дословно
после фирменной подписи. Если оба поля равны `null`, writer также очищает `C16`
и скрывает строку 16. Без metadata строка 16 остаётся неизменной для backward
compatibility. `item_notes` — список явных клиентских сносок. Номер
позиции должен быть уникальным положительным номером строки CSV и не может
превышать количество позиций. Пустой список допустим. Duplicate/out-of-range
номера, пустой текст и неизвестные вложенные поля завершают запуск с FAIL без
output.

Certified tuned_v4 cells:

- `B9` — номер и дата;
- `B10` — плательщик;
- `B11` — объект;
- `B12` — основание / проект;
- `J17:J116` — сноски, привязанные к позициям `1:100`;
- `C16` — строка раздела, очищаемая только при двух `null`;
- `C121` — срок действия;
- `C122` — оплата и поставка;
- `C123` — срок изготовления;
- `A131` — скрытая числовая ставка НДС;
- `H118` — формульная подпись НДС;
- `I118` — формульная сумма НДС.

Формула суммы НДС:

```text
=IF(OR(NOT(ISNUMBER(I117)),NOT(ISNUMBER($A$131))),"",I117*$A$131/(100+$A$131))
```

Она рассчитывает НДС, уже включённый в итог `I117`. Writer не рассчитывает
сумму НДС в Python и не заменяет формулу шаблона.

Native print contract tuned_v4 повторяет эталон №463: A4, portrait,
`scale=54`, `fitToHeight=0`, `fitToPage=true`, без explicit PrintArea. Поля:
left `0.43307086614173229`, right `0.23622047244094491`, top
`0.35433070866141736`, bottom `0.74803149606299213`, header/footer
`0.31496062992125984`. Writer проверяет этот контракт при запуске с metadata и
не заменяет его собственными PDF-настройками.

Certified logo contract проверяется при metadata preflight до candidate/output:
`xl/media/image1.png` должен иметь SHA-256
`18e0f9446c72f8aa80ea833df07c2e42eb830770a0186decc476c5f948987301`;
worksheet relationship должен вести на `../drawings/drawing1.xml`, drawing
relationship — на `../media/image1.png`. Anchor логотипа: col `0`, row `1`,
extent `781050 × 428625`. Missing, modified или broken drawing-chain завершают
запуск с FAIL. Полный hash XLSX не фиксируется: допускаются шаблоны,
совместимые с certified logo/layout contract.

## Технические замены CHINT

Если в линейке CHINT отсутствует требуемый номинал выключателя нагрузки:

- для требуемого ВН 16А можно предложить ВН 20А;
- для требуемого ВН 25А можно предложить ВН 32А.

Такая замена обязательно отражается отдельной `item_notes`-сноской рядом с
конкретной позицией. Скрытая автоматическая замена запрещена: writer не меняет
бренд, аппарат, номинал или состав. Изменение состава требует явного
технического решения Игоря.

## Fail-closed границы

- launcher всегда передаёт certified `--template-capacity 100`;
- input, template и Python executable должны существовать;
- output должен быть новым, а его parent directory должен существовать;
- commercial writer дополнительно запрещает output внутри Git;
- existing technical 5-column workflow остаётся отдельным и неизменным;
- launcher и writer не выполняют Git-команды и не отправляют документы;
- generated CSV/XLSX, client files и временные файлы нельзя добавлять в Git;
- автоматический отчёт не должен раскрывать цены, суммы, итоги или полные CSV
  rows;
- launcher передаёт только optional metadata path; ставка записывается числом,
  а сумму НДС рассчитывает только certified формула tuned_v4;

После успешного запуска результат остаётся internal draft. Обязательны ручная
проверка Игоря и отдельное Human Approval перед любым client-ready
использованием или отправкой.

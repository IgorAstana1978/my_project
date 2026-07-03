# Phase 2.30b: client-style invoice export design

## 1. Назначение

Client-style invoice export — отдельный будущий контур для подготовки счёта в
клиентском оформлении. Он разрешён только после явного approval Игоря и не
является продолжением, режимом или заменой существующего internal draft writer.

Полный безопасный workflow:

```text
price calculator
    -> preliminary price report
    -> Igor approval
    -> commercial CSV
    -> internal draft XLSX
    -> Igor approval
    -> client-style export
```

Client-style export не отправляет документ клиенту. Generated output остаётся
кандидатом для ручной проверки и требует отдельного Human Approval перед
отправкой.

## 2. Почему Нельзя Заменять Internal Draft Writer

Существующий internal draft writer должен остаться отдельным защищённым
контуром:

- internal warnings нельзя молча удалять, скрывать или ослаблять;
- client-style export не должен запускаться автоматически после генерации
  internal draft;
- client-style export должен иметь отдельную явную команду и отдельный output;
- успешный technical `PASS` не является commercial approval;
- успешная генерация internal draft не является разрешением создать или
  отправить client-style документ;
- client-style export не должен менять поведение существующих writer,
  launcher или price calculator.

Internal draft сохраняет safety context и используется для проверки данных.
Client-style output создаётся только отдельным будущим exporter после второго
явного approval Игоря.

## 3. Required Inputs

Будущий client-style export должен требовать все следующие входы:

- approved commercial CSV;
- generated internal draft XLSX или подтверждённые данные, извлечённые из него;
- approved client-style template outside Git;
- approval artifact JSON;
- новый output XLSX path outside Git.

Даже если exporter использует извлечённые данные, исходный internal draft XLSX
должен быть указан для проверки его SHA256 и связи с approval artifact.

Входные XLSX и CSV нельзя изменять. Output должен быть новым файлом, не должен
совпадать ни с одним input и не должен находиться внутри Git-репозитория.

## 4. Approval Artifact JSON

Approval artifact — обязательный машинно-проверяемый документ, фиксирующий
конкретные одобренные входы и клиентские поля. Минимальный контракт:

```json
{
  "approval_id": "unique approval identifier",
  "approved_by": "Igor",
  "approved_at": "ISO 8601 timestamp with timezone",
  "commercial_csv_sha256": "64 lowercase hex characters",
  "internal_draft_xlsx_sha256": "64 lowercase hex characters",
  "template_sha256": "64 lowercase hex characters",
  "invoice_number": "approved invoice number",
  "invoice_date": "approved invoice date",
  "payer_name": "approved payer name",
  "object_name": null,
  "vat_text_approved": "exact approved VAT text",
  "payment_terms_approved": "exact approved payment terms",
  "delivery_terms_approved": "exact approved delivery terms",
  "validity_terms_approved": "exact approved validity terms",
  "return_terms_approved": "exact approved return terms",
  "signer_name": "approved signer name",
  "signer_title": "approved signer title",
  "approval_note": "scope and limitations of this approval"
}
```

`object_name` может быть строкой либо explicit `null`. Остальные обязательные
поля не должны отсутствовать. Поля с approved text должны содержать именно тот
текст, который разрешено перенести в client-style output; exporter не должен
дополнять его догадками или текстом из старого счёта.

Preflight должен вычислить SHA256 фактических commercial CSV, internal draft
XLSX и client-style template и сравнить их с artifact. Любое изменение любого
из этих трёх файлов аннулирует approval и должно завершать запуск fail-closed.
Повторное approval требуется даже тогда, когда изменился только layout
шаблона, метаданные workbook или одна строка CSV.

## 5. Что Можно Брать Из Эталона

Из эталонного клиентского счёта можно использовать только согласованные
layout-принципы:

- клиентскую шапку;
- компактный layout;
- таблицу в колонках `B:I`;
- крупную типографику;
- итоговую строку сразу после последней позиции;
- область суммы прописью;
- явную область печати;
- формат A4 portrait;
- стили и иерархию границ.

Эти элементы следует реализовывать через отдельный approved client-style
template. Нельзя использовать blind copy всего workbook package: в эталоне
могут оставаться старые данные, лишние листы, формулы, media или print settings.

## 6. Что Нельзя Копировать Без Approval

Из эталона запрещено автоматически переносить:

- номер счёта `551`;
- дату эталонного счёта;
- плательщика `ТОО «TDK Energy»`;
- текст `НДС 16%`;
- сроки изготовления или поставки;
- условия `EXW`;
- условия оплаты, возврата, предоплаты или договора;
- подписи, ФИО и должности;
- реквизиты конкретного документа;
- client-ready статус.

Логотип и корпоративные реквизиты должны поступать только из отдельно
утверждённого канонического шаблона. Совпадение текста с эталоном само по себе
не считается approval.

## 7. Предлагаемая Будущая Архитектура

Будущая реализация должна быть изолирована от существующих production
контуров:

- `scripts/preflight_client_style_invoice_export.py` — fail-closed проверка
  входов, approval artifact, hashes и output policy;
- `scripts/export_client_style_invoice.py` — отдельный exporter, создающий
  новый XLSX из approved inputs и approved template;
- `scripts/inspect_client_style_invoice_reconciliation.py` — read-only
  reconciliation готового output;
- `scripts/run_client_style_invoice_export.ps1` — отдельная явная operator
  command без автоматического вызова из commercial launcher;
- `examples/client_style_invoice_approval.example.json` — пример контракта
  approval без реальных клиентских данных.

В Phase 2.30b эти файлы не создаются. Здесь фиксируется только design будущего
контура.

Предлагаемый поток:

```text
approved commercial CSV
  + approved internal draft XLSX
  + approved client-style template outside Git
  + approval artifact JSON
        -> fail-closed preflight
        -> isolated client-style exporter
        -> new XLSX outside Git
        -> read-only reconciliation
        -> manual Igor check
        -> separate Human Approval before sending
```

## 8. Reconciliation

Будущий reconciliation должен fail-closed проверять:

- invoice number, invoice date и payer по approval artifact;
- SHA256 всех одобренных входов;
- item count;
- quantities;
- prices;
- суммы по каждой позиции;
- общий total;
- amount words и его соответствие total;
- VAT text в точности как в `vat_text_approved`;
- отсутствие internal warnings в отдельном client-style output;
- отсутствие client terms, которые не были явно approved;
- нахождение output outside Git;
- успешное открытие workbook;
- согласованность formulas и их результатов;
- print area;
- только ожидаемые visible rows и отсутствие скрытых данных в печатной области.

Отсутствие internal warnings допускается только в отдельном client-style
output после approval. Internal draft при этом не изменяется, и его warnings
остаются на месте.

Reconciliation `PASS` означает только техническое совпадение output с
одобренными входами. Он не является разрешением отправить файл клиенту.

## 9. Red Flags

Будущая реализация должна явно выявлять и останавливать следующие риски:

- static amount words, не связанные с фактическим total;
- formula constants, например `=44512`;
- случайное копирование данных старого клиента;
- hidden rows или неверная print area;
- VAT text, скопированный без approval;
- payment, delivery, validity, return или contract terms без approval;
- generated файл, ошибочно принятый за approved client document;
- изменение input после выдачи approval;
- overwrite существующего output;
- output или реальные клиентские артефакты внутри Git.

Amount words должны вычисляться или детерминированно проверяться против total.
Formula constants нельзя считать надёжным источником approved цены.

## 10. Definition Of Done Для Будущей Implementation Phase

Будущая implementation phase считается завершённой только если:

- preflight работает fail-closed;
- approval artifact обязателен;
- SHA256 commercial CSV, internal draft XLSX и template проверяются;
- любое несовпадение hash останавливает генерацию;
- output разрешён только outside Git;
- existing output не перезаписывается;
- partial output не остаётся после ошибки;
- reconciliation завершается `PASS`;
- internal draft writer, commercial launcher и price calculator не изменяют
  своё текущее поведение;
- internal draft warnings не удаляются;
- client-style export запускается только отдельной явной командой;
- manual Igor check остаётся обязательным;
- перед отправкой требуется отдельное Human Approval;
- exporter ничего не отправляет клиенту автоматически.

Phase 2.30b является design-only фазой: scripts, tests и XLSX в ней не
создаются и существующие production-файлы не изменяются.

# invoice_quote_filler v0.2.1: checked quote smoke runbook

## 1. Назначение smoke helper

`scripts/smoke_checked_quote_launcher.ps1` проверяет happy path checked launcher:
synthetic strict CSV проходит preflight, `make_quote_capacity100_checked.ps1`
запускает generator, temporary output `.xlsx` создаётся, а затем временные файлы
удаляются.

Это manual smoke helper, не production command.

## 2. Когда запускать

Запускать после изменений в checked launcher, existing launcher, CSV bridge или
runtime chain, если нужно быстро подтвердить:

- `Preflight: PASS`;
- `Generation: pass`;
- `Output exists: yes`;
- cleanup temporary CSV/XLSX.

## 3. Команда запуска

```powershell
.\scripts\smoke_checked_quote_launcher.ps1
```

Helper печатает полный output checked launcher и затем compact
`CHECKED_QUOTE_SMOKE_REPORT`.

## 4. Что helper создаёт

Helper создаёт только synthetic files в `$env:TEMP`:

- strict CSV с двумя synthetic rows;
- temporary output path `.xlsx`.

CSV содержит только fake data:

```text
name;unit;quantity;instruments_and_devices;cabinet_type_dimensions_material
ВРУ-SMOKE-1;шт.;1;synthetic devices;synthetic cabinet
ВРУ-SMOKE-2;шт.;2;synthetic devices;synthetic cabinet
```

## 5. Что helper удаляет

После smoke helper удаляет:

- temp CSV;
- temp XLSX.

Cleanup выполняется даже при failure. Успешный report должен показать:

```text
Temp CSV deleted:
yes

Temp XLSX deleted:
yes
```

## 6. Почему smoke synthetic-only

Smoke нужен только для проверки control flow wrapper-а и runtime chain. Для этой
цели нельзя использовать real client CSV, client XLS/XLSX или commercial data.

Synthetic-only input помогает безопасно запускать smoke без риска раскрыть или
случайно обработать клиентские данные.

## 7. Почему `.xlsx` не сохраняется

Generated `.xlsx` в этом smoke — temporary draft only. Он нужен только для
проверки, что generator действительно создал файл. После проверки файл должен
быть удалён.

Smoke output нельзя отправлять клиенту и нельзя добавлять в Git.

## 8. Что делать при FAIL

Если `Result: FAIL`, проверить:

- output checked launcher выше smoke report;
- checked launcher exit code по косвенным признакам report;
- наличие `Preflight: PASS`;
- наличие `Generation: pass`;
- наличие `Output exists: yes`;
- строки cleanup.

Не делать commit/push, пока причина failure не понятна и relevant checks не
прошли.

## 9. Что helper не делает

Helper не должен:

- использовать real client files;
- читать `.xls` или `.xlsx` клиента;
- оставлять temp CSV/XLSX после успешного smoke;
- писать файлы в repo;
- менять template;
- менять source scripts;
- делать commit/push;
- отправлять КП клиенту;
- печатать commercial data;
- печатать tokens/secrets/credentials.

## 10. Запрещённые файлы

Не добавлять в repo и не прикладывать к отчёту:

- `.xls`;
- `.xlsx`;
- generated `.csv`;
- screenshots;
- client files;
- temp files;
- tokens/secrets/credentials.

## 11. Report format

```text
CHECKED_QUOTE_SMOKE_REPORT_START

Mode:
PASS

Checked launcher:
pass / fail

Output created:
yes / no

Temp CSV deleted:
yes / no

Temp XLSX deleted:
yes / no

Result:
PASS / FAIL

CHECKED_QUOTE_SMOKE_REPORT_END
```

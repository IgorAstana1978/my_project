# invoice_quote_filler v0.2.1: operator run card

Короткая карточка оператора: какой CSV взять, какую command запускать, какой
report считать PASS и где остановиться перед отправкой клиенту.

## 1. Какой input брать

Использовать только strict 5-column CSV outside Git.

Создать новый пустой strict CSV template outside Git:

```powershell
.\scripts\create_quote_items_csv_template.ps1 "C:\Users\IgorN\Downloads\items.csv"
```

Команда создаёт новый UTF-8 CSV только с точным 5-column header и разделителем
`;`. Существующий файл не перезаписывается. После создания заполнить позиции и
только затем запускать checked launcher. Template/generated `.csv` не добавлять
в Git.

Если источник - legacy `.xls`, сначала запустить extractor, получить strict CSV
outside Git и вручную проверить CSV.

Не использовать как input для checked launcher:

- `.xlsx`;
- template;
- generated quote;
- client workbook;
- screenshot;
- repo file.

Strict CSV columns:

```text
name
unit
quantity
instruments_and_devices
cabinet_type_dimensions_material
```

Правила CSV:

- 1-100 item rows.
- `quantity` - integer.
- Без price/sum/VAT/currency/term/commercial data.
- Файл должен быть outside Git.

## 2. Canonical command

Запускать из repo root:

```text
C:\Users\IgorN\projects\my_project
```

Canonical operator command:

```powershell
.\scripts\make_quote_capacity100_checked.ps1 "C:\Users\IgorN\Downloads\items.csv" "C:\Users\IgorN\Downloads\Черновик_КП.xlsx"
```

Output `.xlsx` должен быть outside Git. Output file must not already exist.

Direct `make_quote_capacity100.ps1` is low-level/internal only and is not the
main operator path. Использовать low-level launcher можно только после явного
решения Игоря.

## 3. Что считается PASS

Для обычного happy path PASS должны быть:

```text
QUOTE_INPUT_PREFLIGHT_REPORT present
QUOTE_DRAFT_INSPECTION_REPORT present
CHECKED_QUOTE_RUN_REPORT present
Preflight: PASS
Generation: pass
Inspection: pass
Output exists: yes
```

WARN:

- не automatic PASS;
- Manual Igor check required;
- `-AllowWarn` только после того, как Игорь осознанно принимает warnings.

FAIL:

- stop;
- do not use draft;
- исправить CSV/output path и rerun.

## 4. Где STOP перед клиентом

Technical PASS / Inspection: pass / smoke PASS is not commercial approval.
Generated `.xlsx` is internal draft only.

Manual Igor check required.
Separate Human Approval required before sending to client.

Manual check checklist:

- positions;
- quantities;
- equipment text;
- cabinet text;
- layout;
- prices/sums/VAT/terms;
- client message/attachments.

## 5. Что запрещено

- Не отправлять клиенту автоматически.
- Не запускать purchase/workshop/shipment.
- Не добавлять `.xls`, `.xlsx`, generated `.csv`, screenshots,
  client/temp files в Git.
- Не использовать low-level launcher без явного решения Игоря.
- Не считать technical PASS approval на price/scope/schedule.

## 6. Finish после quote workflow changes

Daily / quote workflow finish command:

```powershell
.\scripts\finish_quote_workflow.ps1
```

Default command не трогает clipboard. Для явного копирования полного finish
output в ChatGPT:

```powershell
.\scripts\finish_quote_workflow.ps1 -CopyToClipboard
```

Clipboard output включает `CHECKED_QUOTE_SMOKE_REPORT`, `CODEX_FINISH_REPORT`,
nested `CHATGPT_HANDOFF` и `Quote workflow`. Не добавлять client files или
commercial data в finish report.

Она эквивалентна:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_codex_finish_checks.py --mode fast --include-quote-smoke
```

Команда запускает synthetic quote smoke, а не real client files, и печатает
полный finish report для handoff. Smoke PASS не является commercial approval.
Manual Igor check и отдельный Human Approval before sending to client остаются
обязательными.

## 7. Quick workflow state

Показать короткую read-only памятку по текущему quote workflow:

```powershell
.\scripts\quote_workflow_state.ps1
```

Явно скопировать только static state card в clipboard:

```powershell
.\scripts\quote_workflow_state.ps1 -CopyToClipboard
```

State command не запускает generation, smoke или finish checks. Это quick
reference для оператора, Codex и ChatGPT. По умолчанию clipboard не меняется;
`-CopyToClipboard` копирует только static state card. Команда не является
approval на отправку клиенту.

## 8. Короткий prompt для Codex

Для следующих узких задач использовать:

`docs/invoice_quote_filler_v0_2_1_codex_compact_prompt_card.md`

Карточка содержит короткий шаблон `Repo / HEAD / Task / Scope only /
Guardrails / Checks / Final report`. Расширенный prompt нужен для опасных
изменений: quote generation, templates, dependencies, real client files, Excel
runtime или commercial data.

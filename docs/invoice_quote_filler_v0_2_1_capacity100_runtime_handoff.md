# invoice_quote_filler v0.2.1 capacity100 runtime handoff

Current stable commit: `0eef3dc` (`test: cover capacity100 short item csv`).

## Stable Runtime Template

The current working template is outside Git:

```text
C:\Users\IgorN\Downloads\Фирменный_шаблон_счёта-КП_v0.3_capacity100_tuned_v3_ДиН_ВА-КЭС.xlsx
```

Do not overwrite the source template. Generated `.xlsx` files are draft outputs only and must not be added to Git.

## Runtime Chain

```text
CSV -> run_invoice_quote_extended_from_csv.py -> items bridge -> extended writer -> draft .xlsx
```

The CSV adapter delegates to `run_invoice_quote_extended_from_items.py`, which delegates to the extended writer. Writer logic is not duplicated in the CSV adapter.

## One-command Compact CSV Runner

Internal compact runner:

```text
scripts/run_invoice_quote_extended_from_csv_compact.py
```

Internal chain:

```text
input CSV -> temporary compact CSV -> existing CSV bridge -> draft .xlsx
```

The temporary compact CSV is created in system temp and cleaned up after both success and downstream error. The runner delegates compaction to `compact_invoice_quote_items_csv.py` and generation to `run_invoice_quote_extended_from_csv.py`.

Real visual acceptance:

- Source invoice: счёт №475 ТОО «AB COMPANY-01».
- Generated draft: `C:\Users\IgorN\Downloads\КП_475_AB_COMPANY_one_command_draft.xlsx` outside Git.
- Igor visual result: accepted.

## Windows PowerShell Launcher

Primary user-facing launcher:

```text
scripts/make_quote_capacity100.ps1
```

User-facing command format:

```powershell
.\scripts\make_quote_capacity100.ps1 "C:\Users\IgorN\Downloads\items.csv" "C:\Users\IgorN\Downloads\Черновик_КП.xlsx"
```

Defaults:

- Template path is built from `$env:USERPROFILE\Downloads\Фирменный_шаблон_счёта-КП_v0.3_capacity100_tuned_v3_ДиН_ВА-КЭС.xlsx`.
- Template capacity is `100`.
- Python defaults to the project venv executable.

Internally, the launcher calls:

```text
scripts/run_invoice_quote_extended_from_csv_compact.py
```

Launcher preflight checks:

- input CSV exists;
- template exists;
- python executable exists;
- output does not already exist;
- output parent directory exists.

Windows PowerShell 5.1 parser compatibility is fixed in the launcher via an ASCII-safe default template filename.

Real visual acceptance:

- Source invoice: счёт №475 ТОО «AB COMPANY-01».
- Generated draft: `C:\Users\IgorN\Downloads\КП_475_AB_COMPANY_launcher_draft_v2.xlsx` outside Git.
- Item rows filled: Excel rows 17-37.
- Unused rows start at row 38, are hidden, and have C:H cleared.
- Drawing/media preserved.
- Key row heights accepted visually by Igor.

## CSV Contract

Input CSV must be UTF-8 or UTF-8 with BOM.

Separator: `;`

Required columns, exactly:

```text
name
unit
quantity
instruments_and_devices
cabinet_type_dimensions_material
```

Rules:

- `quantity` must be an integer.
- The other fields are strings.
- Quoted fields are allowed, including embedded `;`, quotes, Russian text, and line breaks.
- Commercial columns are not allowed.
- Price, sum, discount, VAT, currency, term, and price confirmation fields must not be accepted as CSV input.

## Sample CSV

Safe sample input for the capacity100 runtime chain:

```text
examples/invoice_quote_items_capacity100_sample.csv
```

This file contains synthetic test rows only. It is not client data and must not be treated as a client-ready quote.

## User CSV Runbook

Короткая инструкция для Игоря по созданию внутреннего черновика КП из CSV:

```text
docs/invoice_quote_filler_v0_2_1_user_csv_runbook.md
```

## Visual Flow HTML

Self-contained visual process map for the capacity100 runtime chain:

```text
docs/invoice_quote_filler_v0_2_1_capacity100_flow.html
```

## Runtime Guarantees

- Template capacity is `100` item rows.
- Used item rows are visible.
- Unused item rows are hidden.
- Cells `C:H` are cleared on unused rows.
- Formula cells are preserved.
- Drawing/media parts are preserved.
- The safe draft lower block is preserved.
- Output `.xlsx` is an internal draft only, not a client-ready quote.

## Short Item Count Support

- The CSV contract always has exactly 5 allowed columns; this is separate from the number of item rows.
- Capacity100 supports a practical range of 1 to 100 item rows.
- Fewer than 5 item rows is valid. A 3-position CSV is a normal scenario.
- Synthetic regression test: `tests/test_capacity100_short_item_count.py`.
- The test confirms 3 item rows through the compact CSV runner: rows 17-19 are filled, unused rows start at row 20, rows 20-116 are hidden, and C:H are cleared on unused rows.
- A second real smoke test with 3 item rows accepted.

## Adaptive Row Height

Current tuned_v3 width assumptions:

```text
C / name = 28
F / instruments_and_devices = 35
G / cabinet_type_dimensions_material = 24
```

Current height policy:

```text
visual_lines <= 1 -> 24
visual_lines >= 2  -> min(360, visual_lines * 15 + 6)
```

Unused rows always remain:

```text
hidden = true
height = 24
C:H = empty
```

## Safety Rules

- Generated output is not client-ready.
- Do not confirm price, sum, term, equipment composition, or client delivery without Igor.
- Commercial lower block B is not implemented.
- Do not add real `.xlsx` files to Git.
- Do not overwrite the real source template.
- Keep production changes narrow: do not change patcher, builder, CSV bridge, workflow, dependencies, or templates unless a new task explicitly allows it.

## Known Current Status

- `tuned_v3` was opened and visually checked by Igor.
- `draft_v4` was accepted visually by Igor.
- CI is green at the stable commit.
- The runtime chain has been smoke tested end to end:

```text
CSV -> run_invoice_quote_extended_from_csv.py -> items bridge -> extended writer -> draft .xlsx
```

## Real Visual Acceptance

Real invoice smoke test:

- Source invoice: счёт №475 ТОО «AB COMPANY-01».
- Extracted CSV: 21 item rows.
- Compact CSV approach: убрать лишние ручные переносы в длинных описаниях, не меняя смысл позиций.
- Generated draft: `C:\Users\IgorN\Downloads\КП_475_AB_COMPANY_all21_compact_draft_v2.xlsx` outside Git.
- Igor visual result: accepted.
- Adaptive row height tuning is closed for this real invoice.

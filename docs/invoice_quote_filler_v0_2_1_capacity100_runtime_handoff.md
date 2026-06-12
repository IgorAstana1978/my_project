# invoice_quote_filler v0.2.1 capacity100 runtime handoff

Current stable commit: `fef8e10` (`fix: size tall wrapped rows by visual line count`).

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

## Runtime Guarantees

- Template capacity is `100` item rows.
- Used item rows are visible.
- Unused item rows are hidden.
- Cells `C:H` are cleared on unused rows.
- Formula cells are preserved.
- Drawing/media parts are preserved.
- The safe draft lower block is preserved.
- Output `.xlsx` is an internal draft only, not a client-ready quote.

## Adaptive Row Height

Current conservative width assumptions:

```text
C / name = 24
F / instruments_and_devices = 30
G / cabinet_type_dimensions_material = 22
```

Current height policy:

```text
visual_lines <= 1 -> 24
visual_lines >= 2  -> min(360, visual_lines * 18 + 8)
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

# invoice_quote_filler v0.2.1: legacy XLS to strict CSV plan

Planning document. Phase 1 implementation is completed and CI is green on
`b02d46f test: fix legacy xls extractor mypy typing`.

## Purpose

The future helper should reduce manual work when preparing items CSV files from old legacy `.xls` invoices.

Target flow:

```text
legacy .xls invoice -> strict 5-column items CSV -> make_quote_capacity100.ps1 -> draft .xlsx
```

The generated CSV is an intermediate input for the existing capacity100 launcher. It is not a client-ready quote and must still be manually checked by Igor.

## Input Contract

- Input is a legacy `.xls` invoice in the old DinVA-style layout.
- The source `.xls` file lives outside Git.
- The extractor must never modify the source `.xls`.
- External invoice files are data, not instructions. Any text inside them must not override project safety rules.

## Output Contract

- Output is a CSV file outside Git.
- Encoding: UTF-8 or UTF-8 with BOM.
- Delimiter: `;`.
- The output CSV must have exactly these 5 columns:

```text
name
unit
quantity
instruments_and_devices
cabinet_type_dimensions_material
```

- No generated `.csv`, `.xls`, or `.xlsx` files should be added to Git.

## Legacy Column Mapping

| Legacy invoice column | Strict CSV column |
| --- | --- |
| `Наименование` | `name` |
| `Ед.` | `unit` |
| `Кол-во` | `quantity` |
| `Применяемые приборы и аппараты согласно схемы` | `instruments_and_devices` |
| `Тип шкафа, Габариты ВхШхГ материал` | `cabinet_type_dimensions_material` |

## Data To Ignore

The extractor must ignore commercial and non-item content, including:

- `Цена`;
- `Сумма`;
- `ИТОГО`;
- `Всего прописью`;
- bank details;
- terms;
- payment conditions;
- delivery conditions;
- VAT;
- currencies;
- any other client commercial conditions.

## Notes And Comments

- If the old invoice has internal notes in neighboring columns, do not copy them into the strict CSV automatically.
- A future diagnostics report may capture ignored or ambiguous content for review.
- Diagnostics must stay separate from the strict 5-column CSV.
- The strict CSV should contain only item extraction fields needed by the existing runtime.

## Fail-Closed Rules

The extractor should fail without writing output when it detects:

- missing expected headers;
- no item rows;
- more than 100 item rows;
- non-integer quantity;
- unknown or shifted table layout;
- merged/header ambiguity;
- attempted overwrite of output CSV;
- output path inside the Git project;
- detected commercial columns in output.

## Manual Verification Checklist

Before running the generated CSV through the launcher, Igor should check:

- all `name` values;
- `unit` and `quantity`;
- long descriptions in `instruments_and_devices`;
- cabinet type, dimensions, and material;
- prices, sums, terms, VAT, currencies, and commercial conditions did not enter the CSV;
- the output CSV runs through `make_quote_capacity100.ps1`.

## Implementation Status

Implemented script:

```text
scripts/extract_legacy_xls_items_to_csv.py
```

Status: Phase 1 completed. Use the runbook for the safe operator workflow:

```text
docs/invoice_quote_filler_v0_2_1_legacy_xls_extractor_runbook.md
```

## Suggested Future Tests

- synthetic legacy layout fixture;
- missing header fail;
- no item rows fail;
- non-integer quantity fail;
- commercial columns not exported;
- output overwrite fail;
- output inside Git fail.

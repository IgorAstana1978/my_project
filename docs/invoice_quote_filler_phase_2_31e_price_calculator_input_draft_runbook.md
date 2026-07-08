# Phase 2.31e - price calculator input draft builder

## Status and purpose

`scripts/build_price_calculator_input_draft_from_confirmed_composition.py`
creates a JSON price-calculator input draft from a valid Igor-confirmed
composition artifact.

This phase is the bridge:

```text
confirmed composition artifact
-> price calculator input draft
```

It does not execute the price calculator and does not calculate any price.

## Existing calculator input contract

The current read-only calculator accepts a UTF-8 semicolon-delimited CSV with
this exact header:

```text
product_name;cabinet_code;consumables_factor;component_code;component_qty;install_type
```

Phase 2.31e creates a JSON draft containing calculator-compatible columns and
rows under `calculator_input_format`. It does not create a CSV file.

The confirmed composition artifact currently does not contain
`consumables_factor`. The draft therefore marks `consumables_factor` as missing
and requiring Igor confirmation before any future calculator run.

## Command

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\build_price_calculator_input_draft_from_confirmed_composition.py `
  --confirmed-composition-json "C:\outside-git\confirmed-composition.json" `
  --output-json "C:\outside-git\price-calculator-input-draft.json"
```

Report markers:

```text
PRICE_CALCULATOR_INPUT_DRAFT_BUILD_REPORT_START
PRICE_CALCULATOR_INPUT_DRAFT_BUILD_REPORT_END
```

Exit code:

- `0` only when the draft JSON is created successfully;
- `1` on any failure.

## What PASS means

`PASS` means only:

- the confirmed composition artifact validator passed;
- the output JSON path was outside Git and did not already exist;
- the confirmed composition was read;
- the builder mapped confirmed items/components to calculator-compatible rows;
- the draft JSON was written.

`PASS` does not mean price calculation, price approval, commercial CSV approval,
client-ready КП, sending approval or production approval.

## Output policy

The output JSON must be outside the Git project tree. The script fails if:

- `--output-json` already exists;
- `--output-json` is inside the project;
- the output parent directory does not exist;
- confirmed composition validation fails.

If validation fails, no output JSON is created.

## Draft contents

The draft includes:

- `source.confirmation_id`;
- `source.confirmed_by`;
- `source.confirmed_at`;
- `source.source_links`;
- item/product identity;
- quantity;
- cabinet code and label;
- components and install types;
- calculator-compatible columns;
- calculator-compatible rows;
- a safety block.

The safety block states:

```text
status = price_calculator_input_draft_only
derived_from_confirmed_composition = true
price_calculation_executed = false
price_approved_by_igor = false
commercial_csv_authorized = false
client_style_export_authorized = false
sending_authorized = false
production_authorized = false
```

## Safety boundaries

This phase does not:

- call the price calculator;
- calculate totals or prices;
- approve price;
- create commercial CSV;
- create КП or XLSX;
- call a client-style exporter or launcher;
- authorize sending;
- authorize production.

The next phase may run the existing read-only price calculator on a completed
input draft, but any price result still requires Igor review and approval.

## Example PASS report

```text
PRICE_CALCULATOR_INPUT_DRAFT_BUILD_REPORT_START

Status:
PASS

Mode:
price calculator input draft build only

Checks:
confirmed composition validation: pass
output policy: pass
draft read: pass
mapping: pass
draft write: pass
safety boundary: pass

Red flags:
none

Output:
C:\outside-git\price-calculator-input-draft.json

Commercial status:
calculator input draft only; no price calculated; not price approval; not commercial CSV; not client-ready КП

Human Approval:
Igor approval still required before price result, commercial CSV, КП sending or production

PRICE_CALCULATOR_INPUT_DRAFT_BUILD_REPORT_END
```

## Example FAIL report

```text
PRICE_CALCULATOR_INPUT_DRAFT_BUILD_REPORT_START

Status:
FAIL

Mode:
price calculator input draft build only

Checks:
confirmed composition validation: fail
output policy: fail
draft read: fail
mapping: fail
draft write: fail
safety boundary: pass

Red flags:
confirmed composition validation failed

Output:
not created

Commercial status:
calculator input draft only; no price calculated; not price approval; not commercial CSV; not client-ready КП

Human Approval:
Igor approval still required before price result, commercial CSV, КП sending or production

PRICE_CALCULATOR_INPUT_DRAFT_BUILD_REPORT_END
```

## Operator notes

Use this builder only after Igor has confirmed the technical composition. The
created JSON is still a draft. It must not be treated as a calculated price or
commercial approval.

Do not create XLSX, CSV, client, generated or temporary files from this phase.
Do not commit or push without separate Igor approval.

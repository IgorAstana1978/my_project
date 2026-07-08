# Phase 2.31f - completed price calculator input draft validator

## Status and purpose

`scripts/validate_completed_price_calculator_input_draft.py` validates a
completed JSON price-calculator input draft before any future calculator run.

This phase is the bridge:

```text
price calculator input draft
-> completed price calculator input draft validated for future calculator use
```

Phase 2.31e creates an incomplete JSON draft because the confirmed composition
artifact does not contain `consumables_factor`. Igor or the operator must
complete the JSON by filling `consumables_factor` in every calculator row and
adding `operator_completion`.

Phase 2.31f checks only that the completed draft is structurally safe and
complete enough for a future read-only calculator runner. It does not execute
the price calculator and does not calculate any price.

## Command

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\validate_completed_price_calculator_input_draft.py `
  --input-json "C:\outside-git\price-calculator-input-draft.completed.json"
```

Report markers:

```text
COMPLETED_PRICE_CALCULATOR_INPUT_DRAFT_VALIDATION_REPORT_START
COMPLETED_PRICE_CALCULATOR_INPUT_DRAFT_VALIDATION_REPORT_END
```

Exit code:

- `0` only on `PASS`;
- `1` on any `FAIL`.

## Required completion

The completed JSON must keep:

```text
schema_version = price_calculator_input_draft.v0.1
draft_type = price_calculator_input_draft
calculator_input_format.kind = confirmed_composition_csv_rows
calculator_input_format.delimiter = ;
```

The calculator columns must exactly match the existing calculator contract:

```text
product_name
cabinet_code
consumables_factor
component_code
component_qty
install_type
```

`calculator_input_format.rows` must be non-empty. Every row must include those
exact fields. `consumables_factor` and `component_qty` must be positive JSON
numbers. String values such as `"1.08"`, `null`, empty values and zero are not
accepted.

`calculator_input_format.missing_required_fields` must be absent or an empty
list. If it still contains `consumables_factor`, the draft is incomplete and the
validator fails.

`operator_completion` must include:

```text
completed_by
completed_at
completion_note
consumables_factor_confirmed_by_igor = true
```

The report never prints long completion notes, raw source text, rows, prices or
component lists.

## Safety boundaries

The safety block must remain:

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

This phase does not:

- call the price calculator;
- calculate price;
- approve price;
- create CSV;
- create commercial CSV;
- create КП or XLSX;
- call a client-style exporter or launcher;
- authorize sending;
- authorize production.

A future phase may convert or run the existing read-only calculator only after
this validator returns `PASS`. Any future price result still requires Igor
review before commercial CSV, КП sending or production.

## Example PASS report

```text
COMPLETED_PRICE_CALCULATOR_INPUT_DRAFT_VALIDATION_REPORT_START

Status:
PASS

Mode:
completed price calculator input draft validation only

Checks:
JSON readable: pass
schema constants: pass
calculator format: pass
operator completion: pass
safety boundary: pass
rows: pass
forbidden keys: pass

Red flags:
none

Commercial status:
calculator input complete only; no price calculated; not price approval; not commercial CSV; not client-ready КП

Human Approval:
Igor approval still required before price result, commercial CSV, КП sending or production

COMPLETED_PRICE_CALCULATOR_INPUT_DRAFT_VALIDATION_REPORT_END
```

## Example FAIL report

```text
COMPLETED_PRICE_CALCULATOR_INPUT_DRAFT_VALIDATION_REPORT_START

Status:
FAIL

Mode:
completed price calculator input draft validation only

Checks:
JSON readable: pass
schema constants: pass
calculator format: fail
operator completion: pass
safety boundary: pass
rows: fail
forbidden keys: pass

Red flags:
calculator_input_format.missing_required_fields must be absent or empty
field must be a positive number: calculator_input_format.rows[0].consumables_factor

Commercial status:
calculator input complete only; no price calculated; not price approval; not commercial CSV; not client-ready КП

Human Approval:
Igor approval still required before price result, commercial CSV, КП sending or production

COMPLETED_PRICE_CALCULATOR_INPUT_DRAFT_VALIDATION_REPORT_END
```

## Operator notes

Use this validator only after Igor or the operator has completed the JSON draft.
`PASS` means only that the input draft is complete for a future read-only
calculator step. It is not a calculated price, not price approval, not commercial
approval, not client-ready КП and not authorization to send or produce.

Do not create XLSX, CSV, client, generated or temporary files from this phase.
Do not commit or push without separate Igor approval.

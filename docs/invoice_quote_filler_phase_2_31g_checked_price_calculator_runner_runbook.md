# Phase 2.31g - checked price calculator runner

## Status and purpose

`scripts/run_checked_price_calculator_from_completed_draft.py` is the first
checked runner that can execute the existing read-only price calculator from a
completed price-calculator input draft.

This phase is the bridge:

```text
completed price calculator input draft
-> completed input validator
-> temporary CSV bridge
-> existing read-only price calculator
-> draft price calculation report
```

The runner validates the completed JSON draft before it creates any calculator
input. It only runs the existing calculator after
`scripts/validate_completed_price_calculator_input_draft.py` returns `PASS`.

## Command

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\run_checked_price_calculator_from_completed_draft.py `
  --completed-input-json "C:\outside-git\price-calculator-input-draft.completed.json" `
  --price-workbook "C:\outside-git\price-workbook.xlsx"
```

The existing calculator CLI is used exactly as:

```powershell
.\.venv\Scripts\python.exe .\scripts\calc_quote_price_draft.py `
  --price-workbook <path> `
  --input-csv <temporary-csv-path>
```

Report markers:

```text
CHECKED_PRICE_CALCULATOR_RUN_REPORT_START
CHECKED_PRICE_CALCULATOR_RUN_REPORT_END
```

Exit code:

- `0` only on `PASS`;
- `1` on any `FAIL`.

## Temporary CSV bridge

The existing read-only calculator accepts only semicolon-delimited CSV input.
The runner therefore creates a temporary CSV bridge from:

```text
calculator_input_format.columns
calculator_input_format.rows
```

The CSV header is fixed:

```text
product_name;cabinet_code;consumables_factor;component_code;component_qty;install_type
```

The temporary CSV:

- is created with UTF-8 encoding;
- uses `;` as delimiter;
- is created by the operating system temp facility, outside the project;
- is deleted after `PASS`;
- is deleted after `FAIL`;
- must never be committed.

If cleanup fails, the runner fails.

## What PASS means

`PASS` means only:

- the completed input validator passed;
- the temporary CSV bridge was created safely;
- the existing read-only calculator exited successfully;
- the temporary CSV was deleted;
- no commercial, client or production action was taken.

`PASS` is a technical calculator run result. It is not Igor price approval, not
commercial approval, not commercial CSV approval, not client-ready КП, not
sending approval and not production approval.

If the calculator output contains `PASS`, the runner reports it only as
calculator technical status.

## Safety boundaries

This phase does not:

- approve price;
- create persistent CSV;
- create commercial CSV;
- create КП or XLSX;
- call commercial writer or launcher;
- call client-style exporter or launcher;
- authorize sending;
- authorize production;
- change `scripts/calc_quote_price_draft.py`.

Igor must review any draft price result before commercial CSV, КП sending or
production.

## Example PASS report

```text
CHECKED_PRICE_CALCULATOR_RUN_REPORT_START

Status:
PASS

Mode:
checked read-only price calculator run from completed draft

Checks:
completed input validation: pass
CSV bridge: pass
calculator execution: pass
temp cleanup: pass
safety boundary: pass

Red flags:
none

Calculator result:
calculator exit code: 0
calculator technical status: PASS
calculator mode: read-only preliminary price draft
Input rows count: 2
Total preliminary price: 44 512
calculator commercial boundary: preliminary only; PASS is not commercial approval
calculator human approval boundary: required before using price in commercial КП

Commercial status:
draft price calculation only; not price approval; not commercial CSV; not client-ready КП

Human Approval:
Igor approval required before commercial CSV, КП sending or production

CHECKED_PRICE_CALCULATOR_RUN_REPORT_END
```

## Example FAIL report

```text
CHECKED_PRICE_CALCULATOR_RUN_REPORT_START

Status:
FAIL

Mode:
checked read-only price calculator run from completed draft

Checks:
completed input validation: pass
CSV bridge: pass
calculator execution: fail
temp cleanup: pass
safety boundary: pass

Red flags:
calculator returned non-zero exit code: 1

Calculator result:
calculator exit code: 1
calculator technical status: FAIL

Commercial status:
draft price calculation only; not price approval; not commercial CSV; not client-ready КП

Human Approval:
Igor approval required before commercial CSV, КП sending or production

CHECKED_PRICE_CALCULATOR_RUN_REPORT_END
```

## Operator notes

Use this runner only after the completed draft validator is expected to pass.
The runner may calculate a draft price through the existing read-only calculator,
but that result is still an internal draft. Do not transfer it to commercial CSV
or КП until Igor reviews and approves the price in a later explicit step.

Do not create persistent XLSX, CSV, client, generated or temporary files in the
repository from this phase. Do not commit or push without separate Igor approval.

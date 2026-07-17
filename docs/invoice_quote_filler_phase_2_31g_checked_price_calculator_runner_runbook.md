# Phase 2.31g - checked price calculator runner

## Status and purpose

`scripts/run_checked_price_calculator_from_completed_draft.py` is the first
checked runner that can execute the existing read-only price calculator from a
completed price-calculator input draft.

This phase is the bridge:

```text
completed price calculator input draft
-> completed input validator
-> one temporary CSV bridge per item
-> one read-only price calculator execution per item
-> per-item results and overall preliminary total
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

## Item split and temporary CSV bridges

The runner joins `calculator_input_format.rows` back to the audit data in
`items[].components` by product, cabinet and exact component order. Every row
must belong to exactly one item and must match its component code, quantity and
install type. Ambiguous routing or any audit mismatch fails closed before a
calculator execution.

The runner creates one temporary semicolon-delimited CSV per item. The enhanced
internal header is:

```text
product_name;cabinet_code;consumables_factor;component_code;component_qty;install_type;component_label;cabinet_label
```

`component_code` remains audit data. New price lookup does not require it to
equal a workbook label. The calculator normalizes the component label into a
technical signature containing apparatus category, poles, rating,
residual-current parameters where applicable, and install type.

Each approved signature mapping explicitly records worksheet, row, expected
workbook label, material price and work price. Cabinet mappings likewise record
worksheet, row, expected label and price. The exact workbook cells are checked
before use. Unknown or ambiguous signatures, missing worksheets, label drift or
price drift fail closed. The worksheet `Прайс` is forbidden for lookup.

The temporary CSV:

- is created with UTF-8 encoding;
- uses `;` as delimiter;
- is created by the operating system temp facility, outside the project;
- is deleted after `PASS`;
- is deleted after `FAIL`;
- must never be committed.

If cleanup fails, the runner fails.

## UTF-8 process and diagnostic contract

The runner passes `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1` to every child
calculator process. Child stdout and stderr are decoded explicitly with strict
UTF-8. The runner configures its own stdout and stderr for UTF-8 only in the CLI
`main` path and only when the active streams support `reconfigure`.

Technical labels are not transliterated and characters such as `×` are not
replaced to accommodate a local Windows code page.

On a non-zero calculator exit, the runner report contains separate
`Calculator stdout` and `Calculator stderr` sections with the complete captured
text. Empty streams are shown as `empty`. Every line from a calculator
`Red flags` section is also copied into the runner red flags; a traceback is
preserved in full rather than replaced by a presence marker.

## What PASS means

`PASS` means only:

- the completed input validator passed;
- every item CSV bridge was created safely;
- the read-only calculator exited successfully once per item;
- per-item materials, work, cabinet, additional materials and preliminary
  total were parsed and aggregated;
- every temporary CSV was deleted;
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
- modify the source price workbook or technical labels to accommodate a local
  code page.

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

Item results:
item 1: РУ-АВР / ЩРН-24
rows: 2
cabinet price: 7 985
component materials: 16 900
work: 2 700
additional materials: 3 380
preliminary total: 44 512

Overall preliminary total:
44 512

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

Calculator stdout:
<full calculator report, or empty>

Calculator stderr:
<full traceback/error text, or empty>

Commercial status:
draft price calculation only; not price approval; not commercial CSV; not client-ready КП

Human Approval:
Igor approval required before commercial CSV, КП sending or production

CHECKED_PRICE_CALCULATOR_RUN_REPORT_END
```

## Confirmed multi-item regression

On 2026-07-17, Igor authorized one read-only checked regression run for
`CASE-QF-REAL-SMOKE-20260716-001`. The completed input SHA-256 was
`d1b97b9cbcc54fb77a7bd9f0b50c06e383dddec7479ff758a76908fd88c332d6` and the
canonical workbook SHA-256 was
`f8bd69da1f61612d3853e608333486dcd3b6ecd572cd98beb2247c6accb31b5f`.

The runner returned `PASS` with three calculator executions in item order:

- `ЩО-6`: 21 rows, preliminary total `209 553`;
- `НЩР-17`: 13 rows, preliminary total `111 362`;
- `АВР-17`: 12 rows, preliminary total `103 668`;
- overall preliminary total: `424 583`.

All temporary `checked_price_calculator_*.csv` files were deleted. No
persistent CSV, XLSX, PDF or КП was created. Price approval and commercial,
client sending and production permissions remained `false`.

## Operator notes

Use this runner only after the completed draft validator is expected to pass.
The runner may calculate a draft price through the existing read-only calculator,
but that result is still an internal draft. Do not transfer it to commercial CSV
or КП until Igor reviews and approves the price in a later explicit step.

Do not create persistent XLSX, CSV, client, generated or temporary files in the
repository from this phase. Do not commit or push without separate Igor approval.

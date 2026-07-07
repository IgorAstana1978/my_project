# Phase 2.31a — preliminary project/request composition draft contract

## Status and purpose

`scripts/validate_preliminary_composition_draft.py` validates only an untrusted
preliminary composition draft JSON.

This is the first upstream contract toward project/request reading:

```text
project/request/specification text -> preliminary extracted switchboard composition
```

The validator accepts only a preliminary AI-produced draft. It does not parse a
PDF, image, scan or OCR result itself yet.

The draft is not:

- confirmed composition;
- price approval;
- commercial CSV approval;
- client-ready КП;
- production approval;
- sending approval.

Igor must confirm the composition before any price calculator step. A later
phase may transform a confirmed preliminary draft into calculator input.

## Command

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_preliminary_composition_draft.py --input-json .\examples\preliminary_composition_draft.example.json
```

Report markers:

```text
PRELIMINARY_COMPOSITION_DRAFT_VALIDATION_REPORT_START
PRELIMINARY_COMPOSITION_DRAFT_VALIDATION_REPORT_END
```

Exit code:

- `0` only when the report status is `PASS`;
- `1` when the report status is `FAIL`.

## Required root fields

```text
schema_version
draft_id
created_by
created_at
source
safety
items
overall_confidence
red_flags
assumptions
next_required_human_actions
```

Required constants:

```text
schema_version = preliminary_composition_draft.v0.1
safety.status = preliminary_only
safety.confirmed_by_igor = false
safety.price_execution_authorized = false
safety.commercial_csv_authorized = false
safety.client_style_export_authorized = false
safety.sending_authorized = false
safety.production_authorized = false
```

## Source contract

Required fields:

```text
source_type
source_summary
raw_input_sha256
```

Allowed `source_type` values:

```text
text_request
project_fragment
specification
manual_transcription
other
```

`raw_input_sha256` must be exactly 64 lowercase hex characters.

## Item contract

`items` must be a non-empty list.

Each item requires:

```text
item_id
product_name_guess
product_type_guess
quantity_guess
cabinet_guess
components
confidence
evidence
red_flags
assumptions
requires_igor_confirmation
```

Rules:

- `quantity_guess` must be a positive integer;
- `confidence` must be a number from `0` to `1`;
- `evidence` must be a non-empty list of strings;
- `requires_igor_confirmation` must be `true`.

## Cabinet contract

`cabinet_guess` requires:

```text
code_guess
label_guess
confidence
evidence
red_flags
```

Rules:

- `code_guess` can be `null` or a non-empty string;
- `label_guess` can be `null` or a non-empty string;
- `confidence` must be a number from `0` to `1`;
- `evidence` must be a non-empty list of strings.

## Component contract

`components` must be a non-empty list.

Each component requires:

```text
component_id
component_code_guess
component_label_guess
quantity_guess
install_type_guess
confidence
evidence
red_flags
assumptions
requires_igor_confirmation
```

Rules:

- `component_code_guess` can be `null` or a non-empty string;
- `component_label_guess` must be a non-empty string;
- `quantity_guess` must be a positive integer or positive decimal number;
- `confidence` must be a number from `0` to `1`;
- `evidence` must be a non-empty list of strings;
- `requires_igor_confirmation` must be `true`.

Allowed `install_type_guess` values:

```text
null
modular_1p
modular_2p
modular_3p
modular_4p
diff_1p_n
diff_3p_4p
load_switch_1p
load_switch_2p
load_switch_3p
load_switch_4p
mccb_up_to_100a
mccb_125_250a
mccb_400a_plus
manual_review_required
```

## Forbidden keys

These keys are forbidden anywhere in the JSON, recursively:

```text
price_confirmed_by_igor
price_includes_vat
unit_price_kzt
line_total
total_kzt
final_price
client_ready
ready_to_send
send_to_client
commercial_approved
production_approved
confirmed_composition
production_action_authorized
token_execution_authorized
```

If any forbidden key appears, validation fails. If any safety authorization is
`true`, validation fails.

## Report safety

The report includes:

- status;
- mode;
- check names and pass/fail values;
- red flag messages;
- commercial status;
- human approval requirement.

The report must not print raw project text or long evidence blocks. Evidence is
validated structurally but not echoed into the report.

## Example PASS report

```text
PRELIMINARY_COMPOSITION_DRAFT_VALIDATION_REPORT_START

Status:
PASS

Mode:
preliminary composition draft validation only

Checks:
JSON readable: pass
schema constants: pass
source: pass
safety boundary: pass
items: pass
forbidden keys: pass
confidence/evidence: pass

Red flags:
none

Commercial status:
not confirmed composition; not price approval; not client-ready КП

Human Approval:
Igor confirmation required before price calculation or commercial CSV

PRELIMINARY_COMPOSITION_DRAFT_VALIDATION_REPORT_END
```

## Example FAIL report

```text
PRELIMINARY_COMPOSITION_DRAFT_VALIDATION_REPORT_START

Status:
FAIL

Mode:
preliminary composition draft validation only

Checks:
JSON readable: pass
schema constants: pass
source: pass
safety boundary: fail
items: pass
forbidden keys: pass
confidence/evidence: pass

Red flags:
safety.price_execution_authorized must be false
safety authorization is true: safety.price_execution_authorized

Commercial status:
not confirmed composition; not price approval; not client-ready КП

Human Approval:
Igor confirmation required before price calculation or commercial CSV

PRELIMINARY_COMPOSITION_DRAFT_VALIDATION_REPORT_END
```

## Operator notes

`PASS` means only that the preliminary draft matches this contract. It does not
approve prices, does not create commercial CSV, does not create КП and does not
authorize sending.

Do not create XLSX, CSV, client, generated or temp files from this phase.
Do not commit or push without separate Igor approval.

# Phase 2.31d - confirmed composition artifact contract

## Status and purpose

`scripts/validate_confirmed_composition_artifact.py` validates only an
Igor-confirmed technical switchboard composition artifact.

This phase is the bridge after the preliminary review card:

```text
preliminary review card
-> Igor confirms or edits composition
-> confirmed composition artifact
-> future calculator input draft builder
```

The artifact confirms only technical composition. It does not approve price,
commercial CSV, client-ready КП, sending or production.

## Command

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_confirmed_composition_artifact.py --input-json .\examples\confirmed_composition_artifact.example.json
```

Report markers:

```text
CONFIRMED_COMPOSITION_ARTIFACT_VALIDATION_REPORT_START
CONFIRMED_COMPOSITION_ARTIFACT_VALIDATION_REPORT_END
```

Exit code:

- `0` only when the report status is `PASS`;
- `1` when the report status is `FAIL`.

## Required root fields

```text
schema_version
confirmation_id
confirmed_by
confirmed_at
source_links
safety
items
red_flags
notes
next_allowed_step
```

Required constants:

```text
schema_version = confirmed_composition_artifact.v0.1
next_allowed_step = build_price_calculator_input_draft
safety.status = confirmed_composition_only
safety.composition_confirmed_by_igor = true
safety.calculator_input_draft_allowed = true
safety.price_approved_by_igor = false
safety.commercial_csv_authorized = false
safety.client_style_export_authorized = false
safety.sending_authorized = false
safety.production_authorized = false
```

`composition_confirmed_by_igor = true` means only the technical composition is
confirmed. `calculator_input_draft_allowed = true` means a future script may
build a calculator-input draft from this artifact.

## Source links

`source_links` requires:

```text
raw_input_sha256
preliminary_draft_sha256
review_card_sha256
```

Each value must be exactly 64 lowercase hex characters.

## Item contract

`items` must be a non-empty list.

Each item requires:

```text
item_id
product_name
product_type
quantity
cabinet
components
confirmation_note
```

Rules:

- `item_id`, `product_name`, `product_type` and `confirmation_note` must be
  non-empty strings;
- `quantity` must be a positive integer.

## Cabinet contract

`cabinet` requires:

```text
cabinet_code
cabinet_label
```

Both fields must be non-empty strings.

## Component contract

`components` must be a non-empty list.

Each component requires:

```text
component_id
component_code
component_label
quantity
install_type
```

Rules:

- `component_id`, `component_code` and `component_label` must be non-empty
  strings;
- `quantity` must be a positive integer or positive decimal number;
- `install_type` must be one of the allowed confirmed install types.

Allowed `install_type` values:

```text
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
n_pe_bus_set
```

`manual_review_required` is not allowed in a confirmed composition artifact.

`n_pe_bus_set` is the authoritative install type for one combined
`ШИНА N/PE` component representing one N+PE bus set per cabinet. It does not
authorize separate N and PE component identities and must not be used to count
the combined set twice.

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
production_action_authorized
token_execution_authorized
product_name_guess
product_type_guess
quantity_guess
cabinet_guess
component_code_guess
component_label_guess
install_type_guess
confidence
evidence
requires_igor_confirmation
```

If any forbidden key appears, validation fails.

## Report safety

The report includes:

- status;
- mode;
- check names and pass/fail values;
- red flag messages;
- commercial status;
- human approval requirement.

The report must not print long notes or raw source text.

## Example PASS report

```text
CONFIRMED_COMPOSITION_ARTIFACT_VALIDATION_REPORT_START

Status:
PASS

Mode:
confirmed composition artifact validation only

Checks:
JSON readable: pass
schema constants: pass
source links: pass
safety boundary: pass
items: pass
forbidden keys: pass

Red flags:
none

Commercial status:
composition confirmed only; not price approval; not commercial CSV; not client-ready КП

Human Approval:
Igor approval still required before price, commercial CSV, КП sending or production

CONFIRMED_COMPOSITION_ARTIFACT_VALIDATION_REPORT_END
```

## Example FAIL report

```text
CONFIRMED_COMPOSITION_ARTIFACT_VALIDATION_REPORT_START

Status:
FAIL

Mode:
confirmed composition artifact validation only

Checks:
JSON readable: pass
schema constants: pass
source links: pass
safety boundary: fail
items: pass
forbidden keys: pass

Red flags:
safety.price_approved_by_igor must be false
safety authorization is true: safety.price_approved_by_igor

Commercial status:
composition confirmed only; not price approval; not commercial CSV; not client-ready КП

Human Approval:
Igor approval still required before price, commercial CSV, КП sending or production

CONFIRMED_COMPOSITION_ARTIFACT_VALIDATION_REPORT_END
```

## Operator notes

This artifact is not a price approval. A future phase may transform it into a
price calculator input draft, but the price result must still be reviewed and
approved separately by Igor.

Do not create XLSX, CSV, client, generated or temp files from this phase.
Do not commit or push without separate Igor approval.

## confirmed_composition_artifact.v0.2

Schema v0.1 and its preliminary workflow remain unchanged. Validator
dispatches by exact `schema_version`; unknown schemas and mixed v0.1/v0.2
inputs fail closed.

Schema v0.2 is produced only from
`component_replay_applied_bundle.v0.23` and requires the exact applied source
again during validation:

```text
schema_version
project_id
confirmation_id
confirmed_by
confirmed_at
approval
source_lineage
installed_components
reserved_meter_spaces
coverage
confirmed_composition_created
pricing_started
downstream_started
red_flags
```

Required constants:

```text
schema_version = confirmed_composition_artifact.v0.2
confirmed_by = Igor
approval.authority = IGOR_DIRECT_HUMAN_APPROVAL
approval.approved_by = Igor
approval.approval_phrase = CONFIRM TECHNICAL COMPOSITION
source_lineage.applied_bundle_schema_version = component_replay_applied_bundle.v0.23
confirmed_composition_created = true
pricing_started = false
downstream_started = false
red_flags = []
```

`approval.approval_channel` is a required non-empty audit value. This reuses
the existing direct Igor approval phrase; it is not a second approval
mechanism.

`source_lineage` contains:

```text
applied_bundle_sha256
applied_bundle_schema_version
applied_source_lineage
```

The validator recomputes SHA-256 from exact applied bytes and requires
`applied_source_lineage` to equal the complete source lineage object.

`installed_components` is derived from v0.22 direct and cabinet-level
aggregate members. Each record retains exact quantity semantics and uses the
v0.23 approved signature when a correction or reconfirmation exists.
Duplicate and unknown COMP identifiers fail closed.

`reserved_meter_spaces` is an exact separate projection of applied reserved
requirements. Every record must retain `installed_component = false`; its COMP
must not appear in `installed_components`.

`coverage` copies all applied coverage counts and adds
`installed_component_count`. Validator recomputes the source projection and
requires exact equality for installed components, reserved requirements and
coverage.

Schema v0.2 confirms technical composition only. It does not authorize or
start pricing, calculator execution, commercial export, КП, procurement,
production, client send or any other downstream action.

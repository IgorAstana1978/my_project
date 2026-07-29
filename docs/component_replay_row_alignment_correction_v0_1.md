# Component replay row-alignment correction v0.1

## Boundary

`component_replay_row_alignment_correction.v0.1` is a frozen, read-only bridge
artifact. It does not rewrite the cumulative review, field-applicability audit,
PDF extraction, or any evidence ID.

The only allowed corrections are:

| Record | COMP | TFE | Section |
|---|---|---|---|
| `ICF-049` | `COMP-040` | `TFE-018` | `10` |
| `ICF-055` | `COMP-137` | `TFE-063` | `14` |
| `ICF-059` | `COMP-187` | `TFE-085` | `16` |

Each source row contains the combined N/PE identity plus an adjacent
`ЩРН-12` cabinet fragment. The correction keeps `ШИНА N/PE`, detaches only the
adjacent `ЩРН-12` text, and leaves quantity unset for the later authority
decision.

## Root contract

```text
schema_version
case_id
project_id
artifact_status
source_bindings
corrections
safety
```

`artifact_status` is `FROZEN_BOUNDED_ROW_ALIGNMENT_CORRECTIONS`.
`source_bindings` contains the exact SHA-256 of the cumulative review and field
applicability artifacts.

Every correction binds:

```text
correction_id
record_id
component_evidence_id
evidence_position_id
section
action
original_conflict
corrected_component
preserves_original_evidence
creates_new_evidence_id
```

`original_conflict` preserves exact raw designation, type/model, null quantity,
classification, remediation route, and complete component provenance including
PDF SHA and row locator. `corrected_component` is exactly:

```text
component_identity: ШИНА N/PE
detached_adjacent_text: ЩРН-12
quantity_per_cabinet: null
```

## Fail-closed rules

- Exactly the three approved mappings are required.
- Unknown, duplicate, missing, or incomplete mappings fail.
- Source hashes and record/COMP/TFE/section joins must match.
- Raw conflict text and provenance must match the frozen sources byte-for-data.
- Action must be `DETACH_ADJACENT_CABINET_TEXT`.
- Original evidence must be preserved and new evidence IDs must be false.
- Extraction, confirmed composition, pricing, and source mutation flags must
  all remain false.

The validator is
`scripts/validate_component_replay_row_alignment_correction.py`.

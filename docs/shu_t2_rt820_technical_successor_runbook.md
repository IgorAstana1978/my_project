# SHU-T2 RT-820 technical successor runbook

## Scope

`scripts/build_completed_price_calculator_input_v02_shu_t2_rt820_successor.py`
is a case-scoped fail-closed builder for project `2024/086`. It can append four
SHU-T2 RT-820 complete-set rows to the exact immutable 112-row parent only after
a separate publication authorization. It does not calculate or approve a price,
does not create a pricing-profile successor, and does not run any calculator,
resolver, quote, procurement, production, or downstream workflow.

The code-only review phase must use synthetic temporary paths. Loading the three
real inputs through `validate_real_inputs_read_only` is allowed, but calling
`build_successor_payload`, `publish_successor`, or `main` with the real inputs is
not part of code-only validation.

## Immutable inputs

The future publication CLI accepts exactly three input path/SHA pairs:

1. the 112-row completed SHU-T1 additive technical successor;
2. the immutable SHU-T2 RT-820 Human Decision;
3. the applied component lineage v0.23.

The builder rejects a byte-identical copy at another path. It requires the exact
production paths and SHA-256 values embedded in the code, strict JSON parsing
with duplicate-key rejection, and matching lineage bindings in the parent and
Human Decision.

The applied lineage is bound to canonical replay SHA-256
`41ca4e3b63433c8f06c7630565c3d5d5380659e49027bf091a6aff6ab007123e`.
The canonical artifact is not a CLI input and is not added to publication
bindings.

## Evidence and exclusion boundary

The direct immutable SHU-T2 RT-820 Human Decision is the authority for the four
technical rows and their exact eight evidence IDs. The applied component
lineage is used only to verify that every authorized evidence record exists
exactly once and is bound to the exact technical position named by the Human
Decision.

Read-only inspection established an important boundary: applied lineage does
not contain the RT007S outside-cabinet membership structure, while canonical
lineage contains only a historical aggregate count and a general rule alongside
global evidence records. Neither artifact directly classifies the eight SHU-T2
records as outside-cabinet exclusions. Existence in
`$.canonical_component_evidence_records` is therefore not treated as exclusion
membership.

Canonical lineage remains outside the CLI. The builder does not derive, copy,
override, or publish the historical aggregate count. Successor provenance
states explicitly:

- `outside_cabinet_membership_asserted=false`;
- `outside_cabinet_count_transition_asserted=false`.

No `before_count`, `after_count`, remaining-exclusion list, cumulative
unresolved count, or equivalent historical count-transition claim is emitted.
The two count-control flags retained in the Human Decision are validated as a
prohibition against inventing or overriding such a count.

## Technical transformation

The builder preserves the 112-row parent prefix and all 15 cabinet groups. It
changes only the row-ID array of `CABINET-GROUP-003`, appending:

- `ROW-DRAFT-0113`: `TFE-016`, `COMP-031 + COMP-034`;
- `ROW-DRAFT-0114`: `TFE-041`, `COMP-085 + COMP-088`;
- `ROW-DRAFT-0115`: `TFE-061`, `COMP-128 + COMP-131`;
- `ROW-DRAFT-0116`: `TFE-083`, `COMP-178 + COMP-181`.

Each row is one `EKF-RT-820` complete set for one physical SHU-T2 cabinet:

- product `ШУ-Т2`;
- cabinet `CAB-KRN-12`;
- quantity `1`;
- install type `temperature_relay_din_2mod`;
- DIN width `2` modules;
- relay and TST05 evidence retained together as provenance;
- no separate TST05 component, material, work, or pricing row.

Counts are updated by the actual four-row append: calculator rows `112 -> 116`,
SHU-T2 row IDs `8 -> 12`, installed/direct counts each increase by four, and
component groups are derived as the parent count plus the newly absent RT-820
group (`34 -> 35`). All safety flags remain false.

Material `15000 KZT` and work `900 KZT` are recorded only as future pricing
provenance. Generic work `432`, family/fuzzy/similar-relay fallback, pricing,
and calculator execution remain prohibited.

## Future publication CLI

Publication is not authorized by this runbook. After a separate exact Igor
authorization naming inputs, output, and no-overwrite intent, the command shape
is:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\build_completed_price_calculator_input_v02_shu_t2_rt820_successor.py `
  --parent-completed-input "<exact-parent-path>" `
  --parent-completed-input-sha256 "<exact-parent-sha256>" `
  --shu-t2-rt820-decision "<exact-decision-path>" `
  --shu-t2-rt820-decision-sha256 "<exact-decision-sha256>" `
  --applied-component-lineage "<exact-applied-lineage-path>" `
  --applied-component-lineage-sha256 "<exact-applied-lineage-sha256>" `
  --output "<fresh-output-directory>\price-calculator-input-v0.2-completed-shu-t2-rt820-successor.json" `
  --authorization "IGOR_SHU_T2_RT820_TECHNICAL_SUCCESSOR_PUBLICATION_AUTHORIZED"
```

The output directory must not exist. Its parent must already exist. The builder
creates a sibling staging file, writes and fsyncs it, strictly rereads and
validates the staged payload, rechecks all three inputs for TOCTOU, and creates
the final file through an exclusive hard link. It then strictly rereads the
final bytes, validates the complete successor, performs a final TOCTOU check,
and removes staging before printing the success marker.

On any failure, only files owned by that invocation are rolled back. A foreign
replacement of the final path is preserved and reported. Cleanup or post-link
validation failure cannot emit `PUBLISHED_IMMUTABLE_NO_OVERWRITE`.

## Review gates

Before commit authorization, run:

- `py_compile` for the builder and its test;
- Python 3.13 grammar parsing;
- targeted pytest with synthetic inputs;
- full pytest with coverage and an external basetemp;
- Ruff, Black `--check`, and MyPy;
- `git diff --check` and per-file `git diff --no-index --check`;
- read-only validation of the three real inputs.

Do not call real publication merely to validate code. Do not stage, commit, or
push without a separate Git authorization.

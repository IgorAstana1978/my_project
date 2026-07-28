# Component replay readiness bundle v0.1

## Outcome and boundary

The bridge reads original frozen artifacts directly and produces:

```text
schema_version: component_replay_readiness_bundle.v0.1
artifact_status: PRELIMINARY_REPLAY_ONLY_NOT_CONFIRMED
```

It performs a bounded in-memory projection. It creates no normalized
intermediate artifact, confirmed composition, price, commercial document or
downstream authorization.

The cumulative review is the only source of current cumulative state.
Authority batches prove lineage only and are never replayed over that state.

## CLI

Builder:

```text
python scripts/build_component_replay_readiness_bundle.py \
  --intake-manifest PATH \
  --output-dir NEW_DIRECTORY \
  [--validate-only]
```

Validator:

```text
python scripts/validate_component_replay_readiness_bundle.py \
  --intake-manifest PATH \
  --bundle-json PATH
```

`--validate-only` performs the complete direct projection, separate validation
and final input-drift check, then removes private staging. Normal mode atomically
renames staging to a new output directory after full PASS. Overwrite is
forbidden.

## Direct input registry

The intake schema remains `component_replay_intake.v0.1`.

Allowed role/schema pairs are closed:

| Role | Schema |
|---|---|
| `cumulative_review` | `technical_field_component_scheme_completion_review.v0.1` |
| `authority_batch` | `human_decisions_batch.v0.17` |
| `authority_batch` | `human_decisions_batch.v0.18` |
| `authority_batch` | `human_decisions_batch.v0.19` |
| `authority_batch` | `human_decisions_batch.v0.20` |
| `field_applicability` | `unresolved_field_applicability_audit.v0.1` |

Every source descriptor binds:

- `role`;
- absolute read-only `input_path`;
- `schema_version`;
- SHA-256;
- the artifact's own `case_id`;
- common `project_id`;
- `artifact_status`.

The intake root `case_id` identifies the replay operation. It is not required
to equal any frozen artifact case ID.

The loader rejects duplicate paths, missing files, hash drift, descriptor/file
identity mismatch, unknown schema/status and mixed project IDs. Input artifacts
remain in their original case directories and are never copied.

Canonical output source links contain only role, filename, schema, hash, case
ID, project ID and status. Absolute paths are forbidden anywhere in output.
The requested output is forbidden inside every input artifact's case directory.

## Authority lineage

The required chain is:

```text
human_decisions_batch.v0.17
→ human_decisions_batch.v0.18
→ human_decisions_batch.v0.19
→ human_decisions_batch.v0.20
```

The validator checks schema-specific:

- `compatible_with`;
- `prior_batch_id` only for v0.19 and v0.20;
- batch IDs and decision IDs;
- decision-code registries;
- approval authority;
- accepted status;
- original hash, case ID, project ID and artifact status.

The output records lineage metadata and decision-code coverage only.
`replayed_over_cumulative_review` is always false.

## Direct cumulative projection

Each original cumulative position projects to:

- frozen position and review IDs;
- section/document boundary;
- partition;
- positive frozen position quantity and its status;
- component, apparatus and rating evidence entries;
- component absence evidence.

`technical_fields.components.evidence_values` is the identity owner for existing
component evidence IDs. Apparatus and rating evidence may reference only that
same ID set. Joins from the applicability audit must preserve the evidence
position and section bound to each ID.

Missing-ID evidence entries are accepted only as strict `NOT_FOUND`
placeholders: the parent field has `resolution_status: NOT_FOUND`, the entry
has `status: NOT_FOUND`, a null `value`, no `component_evidence_id` key, a
non-empty reason and provenance that passes the normal bounded-path checks.
An explicitly present null or empty evidence ID is rejected.

`components.NOT_FOUND` placeholders:

- do not make a position component-bearing;
- do not enter identified component records;
- remain explicit component absence evidence;
- do not enter component field evidence.

`apparatus.NOT_FOUND` and `ratings.NOT_FOUND` placeholders are validated
field-level absences. They do not enter component absence evidence, component
field evidence or identified component records, and they do not create an
evidence ID, blocker, approval or downstream authorization.

Omitting these field-level absence placeholders from the bounded replay output
does not discard component identity: they contain no component identity, and
the original cumulative artifact remains the hash-bound source of truth.

No evidence ID, quantity, model, rating or install type is invented.

## Count semantics

Builder and validator independently derive and compare:

- `canonical_position_count`;
- `component_bearing_position_count`;
- `component_field_evidence_entry_count`;
- `component_absence_evidence_entry_count`;
- `identified_component_evidence_record_count`;
- `unique_component_evidence_id_count`;
- `position_quantity_total`;
- declared partition totals.

Trust order is:

```text
original artifacts
→ computed in-memory projection
→ intake manifest expectations
→ output validation
```

There is no canonical component count.

## Policy binding

The canonical owner remains `scripts/project_spec_extraction.py`.

The validator:

1. requires a full source commit ID;
2. proves the commit exists in the Git object database;
3. loads the owner blob from that commit;
4. compares the blob SHA-256 with `owner_sha256`;
5. compares the current owner-file SHA-256 with the same value;
6. loads the current owner only after hash equality;
7. verifies `ComponentCandidate`, `Provenance`,
   `classify_component_field_applicability`, and
   `normalize_explicit_component_model_type`.

Current HEAD need not equal the policy source commit. This permits the replay
bridge to be committed after the bound policy commit without weakening policy
lineage.

Policy calls are conformance checks only:

- N/PE records must remain bounded not-applicable classifications;
- meter records must remain model/type semantics;
- bounded РТ 007S and TST05 candidates must be recognized as model/type tokens.

Frozen records remain unchanged in the output. Computed values never replace
them.

## Manifest-bound hard invariants

Project-specific expected values occur only in the intake manifest. The
validator independently recomputes them from originals.

`supply_boundary` binds:

- outside-cabinet exclusion count;
- new evidence-ID count for exclusions;
- externally included row count;
- standalone commercial/pricing/procurement TST05 counts;
- standalone commercial/pricing/procurement РТ 007S counts.

The РТ 007S zero proof is independent of the external-row counter. The manifest
binds the expected SHA-256 and bounded fingerprint of batch 019 decision
`HDA-019-H19-3`; the validator derives the same proof directly from the original
batch and cumulative review. It requires exactly four approved ШУ-Т1 sections
(9, 11, 13 and 15), the RT-820 complete-set commercial name, РТ 007S only as a
bundle member and preserved raw scheme evidence, no standalone РТ 007S
commercial/pricing/procurement representation, and no transfer of the rule to
ШУ-Т2. The canonical output includes only bounded proof metadata and never
source paths.

`complete_set_rules` binds:

- RT-820 complete-set count;
- exact protected component ID, position and raw-quantity records;
- mandatory 5-to-1 protection.

`blocker_requirements` binds:

- quantity blocker count;
- install-type blocker count;
- exact quantity fingerprints;
- exact install-type fingerprints;
- exact preservation.

`policy_binding.expected_classification_counts` binds the full closed
applicability classification registry, including the required 29/16/8
breakdown.

Nonzero expectations reject empty controls, applicability records, blockers or
protected complete-set evidence.

Normalization candidates must retain:

```text
value_applied: false
approval_created: false
not_an_approval: true
```

All confirmed, pricing, commercial and production authorization flags remain
false. Frozen downstream-execution flags are also checked.

## Publication safety

Before publication the builder:

1. validates every direct source;
2. constructs the projection and bundle in memory;
3. independently checks output counts;
4. writes only to a new private staging directory;
5. invokes the separate validator, which reloads the originals;
6. re-hashes the manifest and every input artifact;
7. atomically renames staging to the requested new directory.

Any failure removes private staging and leaves the requested output absent.
No PDF/Excel extraction, confirmed composition, pricing, CSV/XLSX/PDF
generation or downstream workflow is invoked.

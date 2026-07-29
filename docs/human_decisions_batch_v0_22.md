# Human decisions batch v0.22 contract

## Purpose and authority

`human_decisions_batch.v0.22` is a generic, frozen Human Approval artifact for
component quantity and installed-scope decisions. It follows v0.21:

```text
schema_version: human_decisions_batch.v0.22
compatible_with: human_decisions_batch.v0.21
batch_id: 022
prior_batch_id: 021
artifact_status: FROZEN_HUMAN_APPROVAL_DECISIONS
authority: IGOR_DIRECT_HUMAN_APPROVAL
application_status: NOT_EXECUTED
```

The artifact records authority only. It does not apply decisions, run replay,
create confirmed composition, authorize pricing, or start downstream work.

## Source bindings

`source_bindings` contains:

- `canonical_bundle_sha256`;
- `prior_batch_sha256`.

Both values are exactly 64 lowercase hexadecimal characters. The generic
validator checks format and schema binding, but deliberately contains no
project-specific path, SHA, COMP membership, or expected case count.

## Decision kinds

Every entry in `quantity_decisions` has a unique `decision_id`,
`decision_code`, exact technical signature, one or more provenance-linked
members, `accepted_status: APPROVED_BY_IGOR`, the authoritative actor, and
`application_status: NOT_EXECUTED`.

### `DIRECT_COMPONENT_QUANTITY`

`quantity_per_cabinet` is a positive integer and applies independently to every
listed component evidence record. Zero, negative, fractional, or Boolean
quantities fail.

### `CABINET_LEVEL_AGGREGATE`

`aggregate_quantity_per_cabinet` is stored exactly once for the decision.
`members` are evidence coverage, not multiplicative quantity rows:

```text
applies_once_per_cabinet: true
multiply_by_member_count: false
```

The aggregate must never be copied to every member or multiplied by the number
of members.

### `SCOPE_EXCLUSION`

No quantity field is allowed. `scope_status` is one of:

- `NOT_IN_INSTALLED_SCOPE`;
- `NOT_IN_INSTALLED_SCOPE_BY_DEFAULT`.

The decision preserves each component identity and source locator.
`future_inclusion_requires` states the separate approval boundary.
`prohibited_downstream` contains exactly installed composition, pricing,
procurement, and production.

## Membership and provenance

Each member contains:

```text
component_evidence_id
evidence_position_id
section
source_locator
```

A COMP may occur only once in the whole artifact. Duplicate members, duplicate
decision IDs/codes, unknown decision kinds, incomplete objects, and unexpected
fields fail closed.

`component_signature` records cabinet template, component identity, optional
model/type, explicit ratings, optional pole count, and functional role. Missing
model or poles remain `null`; the artifact must not infer them from a generic
name.

## Coverage

The validator recomputes and compares:

- `direct_component_count`;
- `aggregate_member_count`;
- `exclusion_component_count`;
- `union_component_count`.

Counts are artifact-derived and are not hardcoded for any project.

## Safety boundary

The root artifact must state:

```text
confirmed_composition_created: false
pricing_started: false
downstream_started: false
```

`approval_boundary` requires separate approval for batch application and
confirmed composition. `safety_flags` require that the batch is not applied,
replay is not started, and frozen sources are unchanged.

Any numeric field whose key contains `quantity` is rejected when its value is
zero. Scope exclusion is represented by its decision kind and status, never by
`quantity = 0`.

## Validator

Use:

```text
python scripts/validate_human_decisions_batch_v0_22.py \
  --batch-json <human-decisions-batch-v0.22.json>
```

The validator is standalone, read-only, and does not apply the batch.

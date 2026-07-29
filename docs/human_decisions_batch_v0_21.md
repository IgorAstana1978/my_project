# Human decisions batch v0.21 contract

## Authority

`human_decisions_batch.v0.21` follows v0.20:

```text
batch_id: 021
prior_batch_id: 020
compatible_with: human_decisions_batch.v0.20
artifact_status: FROZEN_HUMAN_APPROVAL_DECISIONS
authority: IGOR_DIRECT_HUMAN_APPROVAL
```

It contains exactly one grouped decision:

```text
decision_id: HDA-021-H21-1
decision_code: H21-1
decision_type: N_PE_BUS_SET_AUTHORITY
technical_field: component_identity_quantity_and_install_type
accepted_status: APPROVED_BY_IGOR
component_identity: ШИНА N/PE
quantity_per_cabinet: 1
install_type: n_pe_bus_set
group_expansion_count: 29
separate_n_pe_identities_created: false
anti_double_counting: true
application_status: NOT_EXECUTED
```

`component_mapping` contains exact record/COMP/TFE/section fingerprints for all
29 quantity blockers. The grouped input is only compact authority input; replay
expands it into one immutable audit mapping per COMP.

## Correction prerequisite

The approval boundary requires
`component_replay_row_alignment_correction.v0.1` before applying `COMP-040`,
`COMP-137`, or `COMP-187`. The exact validated correction ID is recorded in
each corresponding audit mapping. Missing or late correction fails.

## Application and audit

Replay preserves source applicability classification, raw values, and
provenance in every audit mapping. It applies the approved combined identity,
quantity, and authoritative install type without modifying a frozen input.

The following fail closed:

- mapping count other than 29;
- duplicate, missing, or unknown COMP/record/TFE/section mapping;
- a split N or PE identity;
- a new evidence ID;
- a conflicted mapping without correction;
- group expansion count other than 29;
- a second correction or v0.21 input;
- a pre-applied/replayed authority artifact;
- any confirmed-composition or downstream authorization.

The validator/application module is
`scripts/validate_human_decisions_batch_v0_21.py`.

# Pragmatic METAL: normalized WU15 decisions adapter v0.1

Read-only adapter `scripts/cabinet_sizing_decisions.py` fixes the mismatch between
the frozen WU15 apparatus and the normalized batch-builder representation.
Selector, planner, HA1 phrase, publication gates and pricing remain unchanged.
Historical raw/structural projections and the default catalogue path are preserved.

## Inputs and authority

Explicit opt-in only: use the existing
`cabinet_sizing.pragmatic_metal_request.v0.1`; its `source_facts` for the three
items point to one external adapter JSON with exactly these fields:

- `schema_version`: `cabinet_sizing.pragmatic_decisions.v0.1`;
- `case_id`: `CASE-TELEGRAM-B4D84204A74200E06B5A18BD371C949ABB899372265FBCDCF2ECF2C898B13A4B`;
- `base_source_fact`: the exact existing WU15 pragmatic review `{path, sha256}`;
- `decisions`: existing `igor_composition_decisions_input.v0.1` `{path, sha256}`.

No new approval schema is introduced. Both the adapter and the batch decisions
file require separate exact admission through the existing
`cabinet_sizing_evidence.AUTHORIZED` role `pragmatic_source_fact`. Admission
requires Igor's direct decision covering the technical fields and exact source
role/path/SHA. Caller hashes, filenames, JSON approval flags, test PASS or adapter
admission alone cannot admit the decisions. This implementation adds no real
entries, creates no decision records and cannot authorize a Case write. Missing
real Human Decisions retain HOLD. These decisions prepare, never replace, HA1.

The base binding must equal the already admitted WU15 pragmatic review. Original
PDF/draft pins are rechecked by the existing reader; manifest/review pins are
checked independently. All three source items and 46 ordered source component IDs
are covered. No synthetic engineering evidence enters real Case processing.

## Permitted normalization

Existing `apply_batch_decisions` is replayed in memory: source hashes, exact ID
coverage, source apparatus quantities, manufacturer, red-flag acknowledgements,
assumption resolutions and supply boundary are checked by the existing contract.
There is no approval prompt or write-capable builder invocation. Frozen original
records/provenance remain in the draft and existing expanded builder audit;
report provenance retains upstream bindings. Sources are reread on recomputation.

This version permits only:

- Exact item names `ЩО6`, `НЩР`, `АВР`; positive integer board quantities copied
  from separately admitted decisions, never inferred from drawings.
- One reviewed manufacturer per board, as required by the batch contract.
- Descriptions exactly `<manufacturer>, <original component_label_guess>` or
  `<manufacturer>, <original label without its leading QF token>`. The latter
  supports grouped decisions. Free-form descriptions remain unsupported.
- Source component codes/quantities unchanged; install types exactly
  `ВА88-32 → mccb_up_to_100a`, `АВДТ32 → diff_1p_n`,
  `ВН-32 → load_switch_3p`.

Even admitted batches cannot substitute ratings/poles/curves/RCD thresholds,
append contradictory electrical text, transfer/omit/duplicate components or use
non-null substitutions. New products requiring different physical evidence are
not established by normalization. `АВР` remains the project designation of the
distribution board; switching automation is not inferred or added.

## Gates and validation

Reconstructed apparatus must exactly match the input apparatus hash. Returned
facts preserve ABSENT source dimensions, unknown installation and prior approval
NONE from existing evidence; they grant no physical-fit authority. Sizing itself
selects cabinets and retains preliminary-only/unverified flags.
`verify_report(..., before_human_approval_1=True)` recomputes via the same adapter.
It remains usable after a separately authorized confirmed directory exists;
read-only verification does not use the publication no-overwrite check as an
input-read restriction. Actual publication retains that check unchanged.

Portable synthetic tests cover 46-ID normalization, recomputation, before-HA1,
the full confirmed-artifact validator and rejection at the final HA1 phrase.
Negative cases attack unadmitted hashes, source drift, missing/duplicate IDs,
unconfirmed fields, electrical substitutions and missing decisions. Synthetic
admission is test-only and establishes no real Case approval.

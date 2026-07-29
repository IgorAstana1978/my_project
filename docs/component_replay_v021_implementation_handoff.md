# Component replay v0.21 implementation handoff

## Scope

Implement only synthetic, contract-level support for Igor's approved N/PE bus
decision:

- preserve the combined `ШИНА N/PE` identity;
- apply `quantity_per_cabinet = 1`;
- apply confirmed `install_type = n_pe_bus_set`;
- expand one grouped authority decision into exactly 29 audit mappings;
- require bounded row-alignment corrections for `COMP-040`, `COMP-137`, and
  `COMP-187`;
- accept `human_decisions_batch.v0.21` only after v0.20.

No real correction, v0.21, intake, or replay artifact may be created or run in
this implementation task.

## Compatibility boundary

The existing v0.17-v0.20 intake and
`component_replay_readiness_bundle.v0.1` output remain semantically unchanged.
A v0.21 intake must contain exactly one versioned correction artifact and use a
versioned v0.2 replay output contract.

## Application order

1. Load and hash-bind all direct inputs.
2. Project the frozen cumulative and applicability records.
3. Validate and project the three bounded row-alignment corrections without
   changing frozen inputs or evidence IDs.
4. Validate the v0.21 grouped authority decision.
5. Expand it deterministically into 29 audit mappings.
6. Resolve the 29 quantity blockers and one install-type blocker in the v0.2
   projection while preserving their source evidence in the audit mappings.
7. Run the existing hard controls, safety checks, builder count checks, separate
   validator, and input-drift checks.

## Fail-closed invariants

- Exact full 29-record mapping, with no duplicate or missing COMP ID.
- Exact correction set: `COMP-040/TFE-018/10`,
  `COMP-137/TFE-063/14`, and `COMP-187/TFE-085/16`.
- Original raw text, source locator, PDF SHA, and provenance are retained.
- No new or split N/PE evidence identity.
- Correction must precede authority application for conflicted records.
- Group expansion count is exactly 29 and every audit mapping is unique.
- Repeated v0.21 or correction inputs are rejected.
- Confirmed composition and every downstream authorization remain false.

## Expected repo changes

- Add narrow correction and v0.21 validator/application modules.
- Extend replay validation/projection conditionally for v0.21.
- Add `n_pe_bus_set` to the authoritative confirmed install-type validator and
  its contract.
- Add synthetic regression coverage only.

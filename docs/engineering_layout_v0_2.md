# Engineering Layout v0.2 — isolated research contract

Entry point: `scripts/engineering_layout_v02.py`. Production and v0.1 entry
points, schemas, policies and historical replay are unchanged. This report is
not accepted by the strict composition/A1 verifier. Every physical result is
HOLD, including conditional geometric witnesses. No Case writes or pricing.

Research policy is fixed at DIN pitch 150 mm and total free DIN resource >=10%;
PANEL free area remains >=25%. Manufacturer keepouts and source facts remain
binding. Unknown factory geometry, mounting, wiring protection/fastening,
termination, actual ports, bend/fill/thermal and installation/IP remain HOLD.

`assess_composition(case_id, items, scenarios, strict_request=None)` reuses the
source-bound v0.1 no-scenario baseline and rechecks it after research. The report
includes the full baseline, its digest and immutable input bindings. Verification
recomputes the whole result. CLI accepts absolute composition/scenario paths,
scenario SHA and writes JSON to stdout only; all outcomes exit 2.

Scenario schema `engineering_layout.scenarios.v0.2` contains 1–16 profiles with
exact fields `id, author, rationale, parameters, future`. All numeric geometry
is SCENARIO, never source admission or Human Approval. Parameters:

- `insets_mm`: six nonnegative top/bottom/left/right/front/back values;
- `route_hwd_mm`: exact mapping DUCTED and RESTRAINED_WIRING to separate positive
  width/depth vectors in mm (the historical name denotes two axes, not HWD);
- `connection_hd_mm`: positive connection height/depth;
- `service_height_mm`: nonnegative reserved lower service height.

Each method consumes its own explicit envelope hypothesis. Both share bounded
trunk/row-branch geometry mechanics; they are not different electrical circuit
designs. RESTRAINED_WIRING reserves conductor routing volume without requiring
DUCT or AUXILIARY products. Positive routing volume is still required: zero
volume does not model safe wiring. Logical N/PE/distribution functions are
separate from products; RCBO load neutrals never become a common neutral node.
No mounting/fastening/protection facts are inferred from this graph. Overcurrent
protection upstream of VN32 remains a required unresolved engineering fact.

Search enumerates row counts and PANEL beside/above DIN, fixed source
orientations only. Empty spare rows retain full source-envelope height;
panel-only and unsupported pair anchors return UNKNOWN. No finite-family failure
is a global physical NO_FIT. KRN36 preserves 3x216/648 mm source capacity;
150 mm row positions are hypothetical and do not replace factory anchors.

`future` has exact fields `status, reference_hwd_mm, policy_binding`:

- REQUIRED: a full positive reference for each present DIN/PANEL zone, with
  body/connection containment, collision and route attachment checks;
- UNKNOWN: empty references and null binding, operational status UNKNOWN;
- NOT_REQUIRED_BY_AUTHORIZED_POLICY: empty references and a path/SHA binding
  admitted by the code-controlled registry. Registry is empty for real inputs.
  JSON approval flags, a matching caller hash or missing references confer no
  authority. Admitted policy bytes and content are rechecked during recompute.

Future objects are not deducted from free space a second time. A REQUIRED
reference is an additional operational criterion, independently of percent.
Historical operational behavior is not changed. No v0.2 research result selects
or approves a cabinet; separate Human Approval and factory evidence remain gates.

# Controlled v0.2 successor draft: project 2024/086

This runbook covers only the fail-closed successor-draft path. It does not
authorize a real successor build, technical-decision application, calculator
run, custom ЩЭ resolver, pricing, CSV/XLSX/PDF creation, or downstream work.

## ШУ-Т1 additive completed-input successor (code-only)

The ШУ-Т1 path uses
`scripts/build_completed_price_calculator_input_v02_additive_successor.py`.
The name is intentional: this builder creates a successor to an already
completed v0.2 input, not a draft successor. The similarly named
`build_price_calculator_input_draft_v02_additive_successor.py` is forbidden.

The parent is exact-bound to the immutable 14-group/109-row completed input
with SHA-256
`71d933c14a603c24ba8072311b84992d1708cbc7ff1fede59727e727218f5bdb`.
All existing cabinet groups and rows remain a deep-equal prefix. The only
allowed append is `CABINET-GROUP-015` plus `ROW-DRAFT-0110..0112`, producing
15 cabinet groups, 34 component groups and 112 rows. The new group represents
four section-aware physical ШУ-Т1 positions without aggregating their pricing
grain.

The builder requires all three direct Human Decision bindings together:

- composition: `bccf62150488037b7df50804c88454119748be103da22dad456db2969126c008`;
- cabinet/pricing: `b3a1bb84bacb2cc5127752cb378b2151552fcb443f02116b12269a086add4247`;
- RT-820 code/install: `95c9f2610a6e8429242789e17c3b69ffae31db28655736aed12caa1d3939630f`.

Path, SHA-256, schema, status, decision ID, direct Igor authority,
`NOT_APPLIED`, immutability and no-overwrite semantics are checked exactly.
RT-820 is one `EKF-RT-820` row with
`temperature_relay_din_2mod`; TST05 remains provenance of that complete set
and never becomes a separate component or charge. Existing AD12 scopes and
mapping018 data are protected by the unchanged parent prefix.

For the exact parent pricing profile with status
`IGOR_INVOICE519_PRICING_PROFILE_APPROVED_NOT_APPLIED`,
`safety_flags.pricing_profile_decision_recorded` must be the boolean `true`:
it records the prior direct Human Decision only. It does not apply the profile,
run pricing, approve a price or authorize downstream work. Every other safety
flag must exist as a boolean when present and remain strictly `false`.

The code-only authorization represented by this repository change does not
authorize executing either builder. The tokens below are only CLI
acknowledgements to be supplied after future separate exact Igor decisions;
their presence in code or documentation is not an authorization.

The technical successor must be authorized and published first. Its builder
accepts only
`IGOR_SHU_T1_TECHNICAL_SUCCESSOR_PUBLICATION_AUTHORIZED`, after a separate
decision naming the exact output path and no-overwrite intent. Publication then
uses private sibling staging, initial and immediate pre-publication TOCTOU
checks, an exclusive atomic no-overwrite link, post-publication
reread/validation and staging cleanup.

The dependent Invoice 519 profile builder is
`scripts/build_invoice519_pricing_profile_additive_successor.py`. It must bind
the newly published completed-input successor by its exact path and SHA plus
the same three Human Decisions. It preserves the 14/51/133/11 profile prefix
and appends 1/4/4/1 to reach 15 groups, 55 section-aware positions, 137
physical cabinets and 12 fingerprints. Each ШУ-Т1 position has multiplicity
1, approved-not-applied unit price 53,763 KZT; the four-position addition is
215,052 KZT and the resulting preliminary candidate project total is
11,841,516 KZT. These values are not final price approval.

Only after the technical successor's exact path and SHA-256 have been checked
may Igor issue a separate decision for the pricing-profile successor. That
builder accepts only
`IGOR_SHU_T1_INVOICE519_PRICING_PROFILE_SUCCESSOR_PUBLICATION_AUTHORIZED`.
The two publication tokens are not interchangeable, and
`IGOR_CODE_ONLY_SUCCESSOR_BUILD_AUTHORIZED` is rejected by both builders. This
corrective code-only authorization permits running neither builder.

## Immutable bindings

- Base draft SHA-256:
  `571647f920f2ffcbfda66339c20be4673eb41127c0534054695c3d4cfc15fbf3`.
- PR correction SHA-256:
  `12d6887edd44c3f13e5b7b5126a8441fa9a6aff350f7eae6ea81da7b4c1abc13`.
- Parent packet SHA-256:
  `1c68b9af8edfef2ca42f89c69e70a873553595d096413f197f9bfe77ec80fc00`.
- Standard cabinet product-name Human Decision SHA-256:
  `889e56687b32948f1a86363069afb7b6ca89b69d4454ee942b6642acce18eafc`.

The builder accepts exactly 18 correction scopes: 10 quantity-and-provenance
rows and 8 provenance-only rows. The other 91 rows and all 14 cabinet groups
must remain deep-equal to the immutable base draft.

`HDA-022` is forbidden only inside `source_quantity` of those 18 affected
rows. Historical `HDA-022` provenance in the 91 unaffected rows and in lineage
is valid and must not be globally filtered or modified.

The successor validator also exact-checks each correction's source quantity
decision against the immutable base, quantity-row versus provenance-only
`superseded_quantity` semantics, and the parent correction path/status/
immutability plus exact per-group correction JSON paths. A publication recheck
read error is a controlled failure and leaves neither output nor staging.

## Separate authorization boundary

Real successor creation is forbidden from an uncommitted implementation.
Independent review, commit, push, and successful repository checks must happen
first. Only then may Igor issue a separate exact real-run authorization naming
the three input paths and hashes, the exact new output path, and no-overwrite
intent. The CLI flag is only an operator acknowledgement of that later decision.

After that decision, the builder command is:

```powershell
python scripts/build_price_calculator_input_draft_v02_successor.py `
  --base-draft-json <EXACT_BASE_JSON> `
  --correction-json <EXACT_CORRECTION_JSON> `
  --parent-packet-json <EXACT_PARENT_PACKET_JSON> `
  --output-json <EXACT_NEW_SUCCESSOR_JSON> `
  --successor-build-authorized-by-igor
```

Publication uses a same-directory staging file, rechecks all three input
hashes, creates the final path exclusively, and removes staging on success or
failure. An existing output is never overwritten.

## Read-only application readiness

Readiness requires the successor draft plus the existing application inputs:
the effective packet, standard product-name decisions, ЩЭ product-name
decisions, AD12 breaking-capacity decisions, and the mapping018 Human Decision,
all with their exact SHA-256 values. It does not require application
authorization and forbids both an output path and
`--application-authorized-by-igor`:

```powershell
python scripts/apply_price_calculator_input_draft_v02.py `
  --draft-json <EXACT_SUCCESSOR_JSON> `
  --expected-draft-sha256 <EXACT_SUCCESSOR_SHA256> `
  --effective-packet-json <EXACT_EFFECTIVE_PACKET_JSON> `
  --expected-effective-packet-sha256 <EXACT_EFFECTIVE_PACKET_SHA256> `
  --sche-product-name-decisions-json <EXACT_PRODUCT_DECISIONS_JSON> `
  --expected-sche-product-name-decisions-sha256 <EXACT_PRODUCT_SHA256> `
  --standard-product-name-decisions-json `
    <EXACT_STANDARD_PRODUCT_DECISIONS_JSON> `
  --expected-standard-product-name-decisions-sha256 `
    889e56687b32948f1a86363069afb7b6ca89b69d4454ee942b6642acce18eafc `
  --ad12-breaking-capacity-decisions-json <EXACT_AD12_DECISIONS_JSON> `
  --expected-ad12-breaking-capacity-decisions-sha256 <EXACT_AD12_SHA256> `
  --mapping-018-decisions-json `
    'C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-MAPPING-018-HUMAN-DECISION-20260807T050634Z\technical-csv-mapping-018-human-decisions-v0.1.json' `
  --expected-mapping-018-decisions-sha256 `
    659e85b8cbb6bf6cf2761176f0603d65a01649d186942af46d90287332a83e06 `
  --readiness-only
```

The standard decision input is hard-bound to its exact external path and SHA.
It must contain 10 ordered decisions covering exactly 77 unique rows. Groups
001–009 and 014 must still have `product_name = null` in the successor; only
the validated application overlay may assign `ПР`, `Щоф`, `ШУ-Т2`,
`ЩАО-1Ж`, `ЩАО-2Ж`, `ЩАО-3Ж`, `ЩО-1Ж`, `ЩО-2Ж`, `ЩС`, and `ЩО-3Ж`.
Groups 010–013 remain exclusively controlled by the separate ЩЭ decision
artifact. The two decision sets must cover all 14 cabinet groups without an
overlap or omission. Source templates, workbook descriptions, and invoice
evidence are never substituted for approved `product_name` values.

The mapping018 input is also hard-bound to its exact external path and SHA. It
must remain an immutable, not-applied direct Human Decision covering exactly
`COMPONENT-MAPPING-018`, review groups 024–029, 16 unique row IDs, and cabinet
groups 010–013. Its row membership, cabinet templates, source evidence, parent
packet lineage, effective-packet coverage, and four approved technical states
are checked exactly. Reordered, missing, extra, duplicate, overlapping, or
inconsistent scope fails readiness.

For those exact 16 rows the application overlay may set only the approved
technical identity: `component_code = EKF-VN-32-2P`,
`install_type = load_switch_2p`, and the authoritative component label selected
by cabinet template. `exact_article` remains `null`; characteristic C and
breaking capacity remain `NOT_APPLICABLE`. The same resolver is used by
readiness and application. No pricing lookup is performed, and neither price,
Invoice №519, nor a workbook label may be used to infer technical identity.

The mapping018 file participates in both initial SHA validation and the final
TOCTOU recheck before exclusive no-overwrite publication. A changed or
unreadable input fails closed, leaves no output, and removes staging.

`PASS` reports contract readiness only. It is not Human Approval and does not
authorize application, calculation, pricing, generated commercial artifacts,
or downstream actions.

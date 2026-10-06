# Post-WU3 future hardening

Direct Igor authority: WU4 A–H implementation request of 2026-10-02.
Only new future Cases participate. `case_state=NEW_FUTURE`,
`future_cases_only=true`, `historical_repricing_authorized=false` are mandatory.
Accepted/historical inputs never migrate or reprice automatically. The accepted
laboratory Case and Invoice519 are explicitly excluded as additional safeguards.
Technical JSON flags/fingerprints assert contract claims, not Human Approval.

## PTO and DRAFT pricing integration

The existing production chain is retained:
`confirmed_composition_artifact.v0.1` ->
`build_price_calculator_input_draft_from_confirmed_composition.py` ->
`validate_completed_price_calculator_input_draft.py` ->
`run_checked_price_calculator_from_completed_draft.py`.
Future confirmed sources add a mandatory `future_context` and per-item
`technical_classification`; no separate production entrypoint is created.
The builder captures the exact absolute confirmed-source path/SHA and applies
PTO/PPN/K as a normalized technical overlay, without rewriting the source.
The checked runner verifies the same binding/overlay before pricing. It uses
the existing calculator's shared canonical arithmetic. Current/historical
profile inputs remain on their original paths and formulas.

Technical classification contains exactly: `family`, `execution`, `circuits`,
`roles`, `categories`, `fuses`, `interlocks`, `overrides`. Every component ID must
have an explicit source role. Power circuits name their exact protection IDs
and conductor section. Missing circuits/protection IDs, ambiguous roles and
conflicting apparatus types HOLD. Control MCBs remain distinct. At >=25 mm²,
when the bound conductor policy requires MCCB, every identified power protection
must actually have an industrial MCCB installation/type and category.
An absent/false optional caller marker cannot bypass this check.

АВР execution must be explicitly STANDARD_CONTACTOR_AVR or BREAKER_AVR and
agree with switching-apparatus roles. STANDARD_CONTACTOR_AVR requires both
source-bound interlocks. Mechanical interlock is never a separately priced row.
A naked caller boolean cannot choose execution or disable a requirement.

Family K is read from the SHA-bound authoritative confirmed Case classification:
1.05 for ВРУ_FUSE/АВР/ШРС; 1.20 for ВРУ_BREAKER/ВРУ-ВА/ЩР/КРН/Я5111/ЯУО.
Wrong/unbound/ambiguous family and changed completed-draft K/rows HOLD. Active
future pricing requires the bound source and exact cost-input JSON/SHA; missing
bindings cannot fall through to the legacy CSV path. Frozen historical/profile
calculation remains separate. Technical PASS does not approve price or send.
Future operator completion contains completed_by/completed_at/completion_note;
it must not claim consumables_factor_confirmed_by_igor. Future K comes from the
bound family/policy, independently of technical-composition and later price
approval. The legacy K Human-confirmation contract is unchanged.

PTO override precedence remains explicit Human decision -> project -> source ->
governed default. Override JSON path/SHA/pointer is part of the bound technical
classification, not a free caller input. Only automation_brand/enclosure_mm are
supported override fields; unknown nested authority/field/binding keys HOLD.
Power protection is invariant: >=25 mm² requires MCCB, with no generic override
or Human exception mechanism. Below 25 mm² no MCCB requirement is inferred.
Default brand is EKF, default VRU
is 1700×800×500. The known exact КЗ-1000В 0,47 мкФ designation maps to Разрядник;
unknown designations HOLD. Source and policy provenance are returned.

For future fuse source components, physical footprint <=160A is PPN-33;
unknown higher footprints are not inferred. Pricing bands are <=100A PN-2 100A,
>100..250A PN-2 250A, >250..400A PN-2 400A. Explicit РЩж_3PH grouping multiplies
one source group into three PN-2 units. Grouping/rating/quantity come from the
bound confirmed source. >400A HOLD; accepted old 630A pricing is not repriced.

The existing checked-runner CLI adds `--future-cost-inputs <JSON>` and
`--future-cost-inputs-sha256 <SHA>`. Cost JSON has `case_id` and ordered `items`,
each exactly `item_id`, `cabinet_cost`, `work_source`. Cost/work records use
absolute JSON path/SHA/pointer; cabinet has role ENCLOSURE_COST. Per-item and
final baseline, technical source, draft and cost bindings are rechecked. The
result is a DRAFT calculation with rule applications/provenance, not a commercial
approval, publication or client-ready document. No real artifacts are written.

## Metal adapter: separate predecessor and candidate, no activation

`governed_metal_cost.py` reuses existing selector/manifest resolution and mapping
fingerprint/snapshot validation for proven Лист1!D52 only. Historical D82 resolver,
bindings and original workbook bytes remain unchanged. B52/C52 never supply cost.

`audit_metal_candidate(candidate, exact_candidate_sha, selector=...)` audits
against the current exact approved metal chain. Without a selector, predecessor
is the exact existing GENESIS_PATH/GENESIS_SHA, independently from candidate SHA.
Explicit `predecessor_source` / `expected_predecessor_sha256` can identify those
same genesis bytes; they do not authorize a different predecessor. The changed
first successor carries its own exact SHA and can be audited read-only.

The adapter compares all source/candidate cell identities/formulas and merges;
only numeric price inputs Лист1!B2/B3 may differ. D52 is deterministically
recomputed. Formula/identity/non-price drift HOLD; price-input and cost diffs
bind predecessor/candidate identities and an approval fingerprint. Source drift
and mixed selector/genesis authority HOLD. Candidate output always requires
separate exact Human baseline approval. There is no materialization, selector
write, activation entrypoint or use of the ordinary main-workbook activator.
УКМ remains excluded.

## Canonical 744-1 content adapter

`build_future_dinva_document.py` reuses the preserved WU3 bridge core/snapshots,
then prepares `dinva_quote_invoice_document.v0.3`. Original WU3 producer bytes
and legacy v0.2 behavior stay unchanged. Default CLI is read-only preflight;
the separate WU6 publication mode is described below:

```powershell
.\.venv\Scripts\python.exe scripts/build_future_dinva_document.py `
  --case-source <EXACT_JSON> --case-source-sha256 <SHA> `
  --case-approval <EXACT_APPROVAL_JSON> --case-approval-sha256 <SHA>
```

Source schema is `dinva_future_case_document_source.v0.1`: existing bridge
source keys plus the future context. Each item additionally supplies reviewed
`technical_display` components: `section`, `label`, `rating`, positive `quantity`,
`unit`, `group_size` (1 or 3), and `source_locator` to that item's full engineering
composition. These are explicit approved Case facts, not an NLP extraction or a
744-1 BOM copy. Full engineering text stays intact. Display aggregation is by
section/apparatus/rating/unit, with exact three-phase conversion and no remainder.
Known numeric fuse groups descend by current within their section as in 744-1;
unknown ratings and other apparatus retain their source order.
Engineering annotations use `unit=note`, `quantity=null`, `rating=""` and
`group_size=1`; their text must occur verbatim in the bound engineering source.
They preserve interlocks/N/supply exclusions without invented counts or prices.
Each display cites the SHA/pointer of its own structured source. The independent
document validator rechecks source/approval/policy bindings and transformation.

The canonical reference is SHA 99ae60e3... of exact №744-1. Bind it with role
`CANONICAL_744_1`; also preserve project/Case upstream bindings. CHINT, old 10A,
old cabinet dimensions, quantities, prices and lead times are never inherited.

Future quotes contain the complete eight commercial rows after the separate
amount/VAT row, including the canonical two-line lead-time condition. Validity
defaults to three banking days; lead time and delivery stay variable. Quote
nouns use счёт/КП as required by Igor's future-quote decision. An unsupported
additional payment/commercial override HOLD, rather than silently disappearing.
Commercial transformations bind source SHA plus policy SHA. Classic v0.5 is
required. Existing layout algorithms/fonts/assets are retained; only the last
three commercial lines receive proven canonical general alignment.

New real source/approval/document JSON and real XLSX require separate exact
Human Approval. WU4 did not materialize them. No tests or
preflight may approve or replace the accepted laboratory quote.

## WU6 reusable future XLSX joins

Only an explicit NEW_FUTURE Case participates. Historical Cases, Invoice519,
and the accepted laboratory Case are excluded. No pricing formula, renderer,
canonical layout, PDF or downstream boundary changes are involved.

### Reviewed composition input

The existing `build_confirmed_composition_from_preliminary_bundle.py` batch
flow adds `--future-review-json` and `--future-review-sha256` together. Both
require `--case-id` and existing `--decisions-json`. The reviewed primary input
has schema `future_composition_review.v0.1`, exact `case_id`, `draft_id`,
`input_sha256` (the same manifest/draft/review hashes as the batch decisions),
`future_context`, and ordered `items`, each exactly `item_id` and
`technical_classification`. It does not assert commercial approval.

The existing classification validator checks those facts against the final
component IDs/types. Reviewed batch manufacturer must match the existing
source-bound future brand policy/override; a mismatch HOLDs before Human review.
Override sources are reread before composition publication. Additional types are allowed only in
this explicit mode. Classification and context appear in the final composition
summary before the existing exact Human confirmation phrase. The immutable
confirmed artifact carries the reviewed context/classification and supply
boundary in notes; its decision audit records the reviewed input path/SHA/facts.
Both primary inputs and the extraction bundle are reread before publication.
PASS is not direct Igor authority to execute this command on a real Case.

### Deterministic intermediate producers

`build_future_case_document_source.py` has three modes. Each input argument
requires its matching `--<name>-sha256`. `--output` must name a new JSON outside
Git, with an existing parent. Default execution is read-only preflight and
prints candidate SHA; it neither creates a file nor issues an authorization.

1. `pricing-input --confirmed <JSON> --operator <JSON>` builds the completed
   calculator input using the existing input builder. The primary operator
   record contains exactly `completed_by`, timezone-bearing `completed_at`,
   `completion_note`; it must not claim price or Igor approval.
2. `calculation --completed <JSON> --costs <JSON> [--selector <JSON>]` invokes
   the existing checked runner and emits `checked_future_pricing_result.v0.1`.
   Costs retain the existing exact per-item ENCLOSURE_COST/work source contract.
   The result contains ordered item IDs/quantities/unit prices/line totals/grand
   total, rule applications and exact bound inputs. It is DRAFT_NOT_APPROVED.
3. `document-source --confirmed <JSON> --calculated <JSON> --reviewed <JSON>`
   rebuilds and compares the checked result, then prepares the existing future
   document source. The reviewed primary business input has schema
   `future_document_review.v0.1`, `case_id`, existing bridge `metadata`/`terms`,
   `approved_grand_total_kzt`, `source_bindings` (including CANONICAL_744_1),
   and ordered `items`. Each reviewed item contains exactly `item_id`,
   `quantity`, `approved_unit_price_kzt`, `approved_line_total_kzt`, `unit`,
   `technical_display`. Display facts remain explicitly reviewed source facts;
   no NLP, quantity inference, manufacturer/rating choice or substitution occurs.
   Each reviewed apparatus display also names its exact `component_id`. IDs
   must cover confirmed components once in source order and quantities must
   agree (an explicitly classified FUSE_GROUP expands to three physical units).
   The producer removes this input-only ID from the existing document display
   shape. Notes have no component ID/count and require exact engineering text.

The producer copies names, enclosure and complete component text from confirmed
composition, including supply notes; it copies exact checked prices. Reviewed
IDs/quantities/prices/totals must agree. Metadata, amount words and commercial
conditions require their original authoritative review; no historical conditions
are inherited. The existing v0.3 adapter validates the eight canonical rows.

Each candidate can be materialized only by separate `--publish --authorization`
execution after direct Igor approval for the exact action, inputs, output and
no-overwrite intent. The token is ordered:
`IGOR_FUTURE_FLOW_ARTIFACT_PUBLICATION_AUTHORIZED|ACTION=<mode>|CANDIDATE_SHA256=<SHA>|INPUTS_SHA256=<SHA>|OUTPUT_PATH_SHA256=<SHA>`.
INPUTS_SHA256 covers the canonical encoded ordered path/SHA snapshot bindings,
including producer policy. OUTPUT_PATH_SHA256 covers UTF-8 resolved absolute path.
The Python API exposes the same binding for synthetic acceptance; it is not a
Human approval generator. All intermediate JSON is produced by these commands,
rather than assembled by an operator.

### Price/terms Human gate and approved v0.3 publication

After reviewing the exact generated source, Igor must separately approve its
composition, prices, terms/lead time and rendering. Supply the existing separate
`dinva_case_document_approval.v0.1` input with exact source SHA and business
fingerprint, provenance and all existing required flags. Neither producer nor
calculator manufactures that approval. Client send must remain false.

Production `build_future_dinva_document.py` preflight now requires the full
bound composition/calculation/business-review graph. It regenerates the source
and compares exact bytes, including lead time. The verified calculation leaf snapshots
are also direct document provenance bindings, so the unchanged renderer and
independent validator reread them after publication; changed prices, costs,
selector, overrides or producer policy HOLD before rendering.
The explicitly gated old synthetic
content/layout preview remains available; an unbound preview cannot publish.

After separate exact direct publication approval, invoke the existing four
case-source/case-approval path/SHA arguments plus `--output <NEW_JSON> --publish
--authorization <EXACT_TOKEN>`. The ordered token is:
`IGOR_DINVA_FUTURE_DOCUMENT_PUBLICATION_AUTHORIZED|ACTION=IMMUTABLE_DOCUMENT_V0_3_PUBLICATION|CASE_SHA256=<SHA>|APPROVAL_SHA256=<SHA>|DOCUMENT_FINGERPRINT=<SHA>|DOCUMENT_SHA256=<SHA>|OUTPUT_PATH_SHA256=<SHA>`.

Publication regenerates the plan, rejects in-memory modification, stages/fsyncs
exact bytes, rereads the full input graph, and hard-links without overwrite.
It rereads after publication and rolls back only an output whose identity proves
ownership. Existing/foreign/raced outputs are never deleted. Publication does
not render XLSX or permit downstream actions.

After the separate exact renderer authorization, feed the published v0.3 JSON
and SHA to the Classic v0.5 renderer and independent XLSX validator.
The WU6 renderer safety fix changes ownership/rollback only. A successful link
records the candidate's device/inode identity and requires an available nonzero
inode before link; final identity is checked before
and after validation. Rollback deletes final output only after successful link
and a matching actual lstat identity. Pre-existing/raced/foreign replacement or
unverifiable outputs are preserved. Layout/content/style/formulas, document
contracts and Human authorization requirements remain unchanged.
Igor's native Excel visual review remains mandatory. No real execution is
authorized by tests, JSON flags, preflight PASS or this runbook.

Synthetic acceptance in `tests/test_future_case_xlsx_flow.py` starts from a new
bundle and reviewed primary inputs, uses every intermediate producer, pauses at
the simulated composition and price/terms gates, publishes v0.3 and renders a
validated temporary XLSX. Negative cases cover missing gates, exact SHA drift,
item/quantity/price/total/lead-time mismatches, frozen Cases, overwrite, subject
substitution, foreign publication races and owned rollback. No accepted artifact
is modified and no real Case/approval/price/XLSX participates.

## PDF exporter and independent validation

Human Decision 2026-10-05: WU4 closes fail-closed. Trusted real-PDF Human
approval/export is NOT_IMPLEMENTED_PENDING_WU5. No production PDF can execute
through the WU4 exporter. No approval artifact, old token, cached contract,
mutable rollout log or runtime declaration can enable it.

Two production trust gaps were proven in v4:
1. Codex sandbox defaults do not establish non-writability for every execution
   route. A permitted unsandboxed subprocess runs as the sessions owner IgorN,
   with Medium integrity and no restricted SIDs. Read-only ACL/AccessCheck
   evidence grants create/write/delete and DACL/owner rights. No write probe was
   performed. Host-owned rollout JSON is not independent Human authority.
2. Same-run preflight snapshots/rechecks detect mutations during one execution.
   The v0.1 approval did not bind approved exporter/native-engine bytes/version;
   changed implementation could be captured by a later preflight while the same
   input/output/runtime approval remained valid.

WU4 does not implement a signing/key/trust architecture or a production approval/
implementation manifest. Both questions move explicitly to WU5 under separate
Human-approved scope. Old dinva_pdf_export_approval.v0.1 and production runtime
contracts are not sufficient authority. Their production parsing/validation and
rollout-log authority machinery have been removed, not retained as a fallback.

Production API export(...) and legacy _export(...) always raise the deterministic
NOT_IMPLEMENTED_PENDING_WU5 HOLD before reading any plan/approval/runtime inputs
or invoking any engine. CLI production intent (--export, --output and old approval/
authorization/inspector arguments) returns the same HOLD before input processing.
There is no environment/JSON flag that re-enables production.

Useful read-only preflight remains: exact profile/document/XLSX bindings and the
independent XLSX validator, upstream-source rechecks and snapshot preservation.
It reports READ_ONLY=true, PRODUCTION_PDF=NOT_IMPLEMENTED_PENDING_WU5 and
CLIENT_SEND=CLOSED. Preflight PASS is technical evidence, not export permission.

The independent inspect_dinva_pdf.py remains a read-only text/font/logo/glyph/
clip validator. It verifies exact PDF/expectations SHA and returns runtime/script/
subject identity receipts. Those checks do not implement trusted production
Human authority or authorize publication/send.

Only export_test_only is executable. It requires TEST_ONLY_DINVA_PDF_EXPORT,
explicit renderer test mode, CASE-TEST-ONLY source identity, SYNTHETIC composition
approval, a test plan, and source/profile/document/XLSX/output sharing an owned
subdirectory of the system temporary directory. Accepted/real Case subjects and
outside-temp outputs HOLD. No TEST-ONLY CLI export mode is exposed.

Native .ps1 direct execution remains closed before any COM/write action. Its
source-bound template is decoded only inside the isolated TEST-ONLY path. Hidden
Excel opens only the synthetic XLSX read-only, with macros/events/links disabled,
exports to owned staging, closes without saving and quits its own instance.
Literal-quoted paths and fixed system PowerShell invocation are retained.

TEST-ONLY PDF conformance retains exact installed font embedding, independent
native clip measurement/recovery and final content/font/logo/geometry validation.
Runtime/inspector/PDF/expectations identity drift HOLD inside this test contour.
Atomic no-overwrite output and rollback of only the owned output inode remain.
The output embeds DINVATestOnly=true and DINVAProductionPDFStatus=
NOT_IMPLEMENTED_PENDING_WU5. The API returns PASS_TEST_ONLY, test_only=true,
production_export_authorized=false and client_send_authorized=false.
No production approval/runtime-contract sufficiency is claimed in these receipts.

Synthetic smoke uses DINVA_PDF_NATIVE_TEST=1,
DINVA_PDF_INSPECTOR_PYTHON=<test inspector Python> and optionally an existing
approved presentation profile at DINVA_PDF_NATIVE_PROFILE. Only synthetic
XLSX/PDF are authored; accepted/historical artifacts and A–G remain unchanged.

Full gates remain pytest/100% src coverage, Ruff, Black check and MyPy. Commit,
push, real publication/client send/activation/downstream remain CLOSED.

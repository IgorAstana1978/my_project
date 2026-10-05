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
and legacy v0.2 behavior stay unchanged. CLI is read-only preflight only:

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
Human Approval. This implementation does not materialize them. No tests or
preflight may approve or replace the accepted laboratory quote.

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

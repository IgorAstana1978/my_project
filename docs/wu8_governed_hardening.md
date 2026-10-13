# WU8 permanent governed hardening v0.1

Direct Igor implementation authority: WU8 request and CONTINUE WU8 instruction,
2026-10-13. Published starting baseline: 09db707add4f1860dd1c4da44e6593e1f74388ab.
Scope is future-only. WU7, Invoice519, real approvals, real quotes, publication,
Git staging/commit/push, client send and downstream remain outside this execution.

## Recorded direct Human Decision

`IGOR-WU8-AVR-MOTOR-DRIVE-20261013`, from the direct CONTINUE WU8 user message:

- Each `Автомат` price is for one breaker of the corresponding exact rating.
- Each `Привод` price is for one drive of the corresponding exact rating.
- Г-Г and Г-Д have two switched inputs: two breakers and two drives.
- Г-Г-Д has three switched inputs: three breakers and three drives.
- Work is separate, from that topology's authoritative rating work table.
  Breaker/drive prices neither include nor replace work.
- 630A always HOLDs without source-bound confirmation of drive availability.

The literal runtime decision is `AVR_DECISION` in `wu8_governed_sources.py`.
Calculation and document provenance bind that policy's exact path/SHA. This is
the record of Igor's actual technical decision, not a generated Case approval
or price/lead-time authorization. It is bound to workbook SHA
02ca5be9b2eb6775289ee1053c389a659c85e2bd27a2b9867b7d523d6d6e4096.

## Exact source resolvers

`python scripts/wu8_governed_sources.py` is a read-only reproducible audit.
It resolves the active pointer/manifest and checks the exact approved SHA.
Downloads and same-name workbooks are never searched or used as fallback.
Metal authority remains the existing GENESIS_PATH/GENESIS_SHA, SHA
b51d7087e0bd8f92e48985294062ead6826c6b50ce3cfacd0f9d0dc22c05f7f2.

The ten-size whitelist is common to already supported families. Exact confirmed
cabinet dimensions and source-bound sizing overrides must agree. No nearest,
bigger, default or price-based selection occurs. Individual D22/28/35/42/44/46/
52/51/53/54 cost formulas are proven separately, with all literal inputs and
formula dependencies retained. Other D cells and sales B/C outputs are excluded.
ЩРн/ЩРН → КРН and ЩРв/ЩРВ → КРВ are pricing/cost/display aliases.
The confirmed cabinet_code selects an exact audited identity, never arbitrary
designation text. Raw designation remains unchanged in the SHA-bound composition
and document source, separately recorded as source_designation in checked cost.
For example CAB-KRN-18 displays exactly КРН-18 even when its raw designation is
`ЩРн 18з-1 36 УХЛ3 IP31`. Missing/ambiguous identity HOLDs.
Executable main-sheet cost mappings cover КРН-12/18/24/36/48/54/72/96 (L6:M13)
and КРВ-12/18/24/36/48/54/72 (L18:M24). The read-only audit separately proves
each main M cost equals the exact named metal D61:D68 or D74:D80 cost formula.
No dimension-only substitution between equal-size named cabinets is allowed.

ЩР rows 8, 9, 15–19 have exact executable signatures. Row 9's 3P mapping is
the WU7 mapping explicitly reiterated in the WU8 request. Other breaker rows
are inventoried with HOLD reasons where poles, characteristic or rating are
absent. No C characteristic, unstated pole count, continuous range between
enumerated nominal values, new apparatus or family is inferred.

Confirmed categories `MCCB AVR <topology> <rating>A` and
`CONTACTOR AVR <topology> <rating>A` carry explicit topology and nominal facts
inside the existing technical-classification categories, without a new schema.
Motor ratings are exactly 100/160/250/400/630A. Each breaker row includes
separate AUTOMATIC and DRIVE source records and their exact quantities.
Contactor nominal matches are exact; no nearest contactor substitution occurs.
The complete contactor inventory is 18–800A on Г-Г and Г-Г-Д and 18–1000A
on Г-Д (enumerated exact nominal rows, not a continuous range). Г-Г-Д 800A
uses A36/B36 material (282000 per contactor) and J8/K8 work (41440 separately).
Г-Г 800A and Г-Д 800/1000A have material authority but no corresponding work:
the audit records explicit HOLD_MISSING_TOPOLOGY_RATING_WORK_AUTHORITY.
They cannot calculate using 630A or any nearest/default work. Motor-drive
ratings remain exactly 100/160/250/400/630A.
Successive ordered `до` work ceilings define disjoint work bands; the selected
row retains both boundaries, label/cell, value and topology. There is one
switching group per supported AVR item. Missing/mixed groups HOLD.

For 630A the existing SHA-bound work-source JSON must include
`avr_drive_availability`, an existing-style path/SHA/locator binding. Its value
has exactly rating_a=630, available=true, nonempty confirmed_by and
confirmation_reference. This record represents availability evidence, not Case
or commercial approval. Missing/false/malformed/changed evidence HOLDs. The
evidence file is reread and included in the upstream document snapshot graph.

## Two meaningful future business approvals

1. Igor confirms exact engineering composition through the existing composition
   confirmation gate. Source roles/categories/cabinet facts stay SHA-bound.
2. After autonomous source resolution, calculation and safe verification, Igor
   approves exact price, lead time and permission to form the branded quote.

Existing write-capable execution tokens and no-overwrite output binding remain
mandatory. They do not create additional business decisions or Human authority.
The second approval must explicitly cover the exact artifact actions/inputs/
outputs before execution. After Human Approval #2, native/visual QA is technical
verification, not a third meaningful technical/commercial Human Approval while
approved values and content are unchanged. QA requiring a change to an approved
value/content returns to Human Decision before applying it. Client send and
publication remain separate Human Approval/red boundaries.
No technical PASS can manufacture either approval. Synthetic tests may simulate
these gates; no real Case approval, activation or quote is created by this job.

Future v0.3 Classic presentation uses шт., approved cabinet aliases, exact fifth
header `Применяемые приборы и аппараты согласно схемы`, and a short canonical
top lead-time header. The full approved clause remains in the bottom commercial
block. Legacy document versions retain their existing presentation behavior.

Future enclosure row sizing uses word wrapping under the existing dynamic
height rule. Native Excel measured the synthetic regression at 39 pt before
the fix versus 56.25 pt needed by AutoFit; after the fix the rendered height is
57 pt and the same native AutoFit requires 56.25 pt. These checks open a separate
hidden Excel instance read-only, close without saving, and verify unchanged
XLSX SHA. Fonts, widths, grid, formulas, height limits and legacy sizing remain.

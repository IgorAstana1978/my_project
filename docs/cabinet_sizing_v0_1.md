# Cabinet Sizing v0.1 — automatic contract, Device Envelope v0.2

Direct Igor decisions: Device Envelope v0.2, Cabinet Reserve Policy v0.1 and
Source Cabinet Dimensions Precedence v0.1 (2026-10-19; continued 2026-10-20).
This supersedes the supplied-layout verifier as the new before-HUMAN_APPROVAL_1
path. Technical PASS grants no Human or downstream authority.

The 2026-10-20 Pragmatic METAL v0.1 decision adds the separate preliminary path
below. The original exact-interior automatic path and historical replay remain
available. Interior/install proof is mandatory for that exact path; preliminary
METAL proposals explicitly retain unknown IP, installation and factory layout.

## Inputs and authority

`cabinet_sizing.size_composition(case_id, items, request=None)` automatically
derives layout and cabinet choice. Neither caller-selected cabinet nor per-Case
placements is accepted by `cabinet_sizing.auto_request.v0.2`. Its exact fields:
`schema_version, case_id, devices, catalogue, source_facts`.
The first two source bindings are reusable evidence; source_facts maps item IDs
to independently pinned project and approval-history facts. Bindings are exactly
`{path,sha256}`. Only the code-controlled role/path/SHA registry
`cabinet_sizing_evidence.AUTHORIZED` admits sources. JSON approval claims or
matching hashes do not grant authority. Duplicate keys, drift, missing raw bytes,
non-absolute/reparse paths and unsupported facts HOLD. No network or price lookup.

Default device evidence is the independently reviewed local WU15 v0.2 assessment,
SHA `cf09e8a17f0017d170cfd82d612caa6d51b1891c4719c5824c04d4111f0188ae`.
Underlying official PDFs/card are rehashed. Sufficient reference records alone
contribute to homogeneous mounting/form-factor axis-wise MAX envelopes;
manufacturer is provenance only. No average, brand ranking, closed-brand roster
or adjacent-execution inference. Exact Decimal millimetres retain fractions.
Mounting anchors must be explicit: overall dimensions do not prove rail offsets.

Default cabinet interior authority is EMPTY. Existing CABINETS / METAL_SIZES
prove approved identities and outer HWD only. Admitted reusable cabinet evidence
must prove exact identity, outer HWD, installation, IP/shock compatibility, disjoint
usable rectangular zones, mounting planes, rails or panel material/thickness and
barrier compatibility. Static obstructions/unusable areas cannot enter usable
capacity. No usable geometry is inferred from outer sizes.

## Layout, reserve and source precedence

DIN devices use actual widths without extra gaps unless required by the source.
Supported default rail pitch is140mm. Unsupported factory-specific geometry HOLDs.
Panel edge clearance is at least50mm top/bottom,20mm sides; larger factory
constraints prevail. VA88 assembly H253 and body H151.2 remain distinct:
A122.5 is measured from body. Total protrusion101.8 fits within either A bound
without assuming a symmetric split. Multiple body-reference assemblies with
unproved pair anchors HOLD; doubled edge boxes never prove a smaller cabinet unfit.

DIN occupied length (actual width and required gaps) is at most75% of proved
usable rail length. Panel occupied area is the sum of conservative physical
envelope H×W, at most75% of proved usable panel area; required clearances pass
an independent geometry check. This area measure does not assert future device
fit in every remaining square millimetre. Mixed zones pass independently.

Panel search enumerates fixed-orientation pair separation constraints and both
orders along each axis. DIN search explores classes/order and rail assignments.
Bounded exhaustion or unsupported cross-rail interactions HOLD. Search uncertainty
cannot justify a larger cabinet. No caller placements are consumed.

Project dimensions are separate pinned source facts, never item.cabinet output.
Facts bind Case/item/apparatus, ABSENT or EXPLICIT source HWD, installation and
known prior approval state. Unknown facts HOLD. Explicit HWD restricts validation
to that exact size; no enlargement/fallback. Absent HWD permits only a unique
componentwise smallest valid approved cabinet. Equal/incomparable alternatives
without a unique minimum HOLD. Any later cabinet/dimension change requires new
direct Human Approval; automatic shrink is forbidden.

## Workflow, replay and current WU15

Builder automatic classification omits manual cabinet code/label corrections.
Batch decisions may supply only cabinet red-flag acknowledgements, or omit that
block when none are required. Old supplied choices do not drive sizing.
Apparatus decisions remain. Final review shows cabinet type and HWD.
Request, raw source and recomputed report checks run before the phrase, after it
and inside atomic publication; no overwrite or approval bypass.

New reports use `cabinet_sizing.auto.v0.2`: Case, complete apparatus, policy,
source constraints, candidate catalogue, envelopes, derived layout and reserve.
`verify_report(..., before_human_approval_1=True)` and validator
`--before-human-approval-1 --expected-case-id` require the automatic schema.
Historical `cabinet_sizing.v0.1` supplied-layout reports remain readable and
recomputable; they cannot satisfy the new gate. Historical applied-component
replay and protected extraction/pricing/Telegram owners remain unchanged.

Read-only CLI: `.venv/Scripts/python.exe -B scripts/cabinet_sizing.py
--case-id <CASE-ID> --composition-json <PRELIMINARY-JSON>`.
Explicit exact-interior WU15 requests for ЩО6/НЩР/АВР still reach
`HOLD_MISSING_CABINET_USABLE_INTERIOR_INSTALL_EVIDENCE`, exit2.
No cabinet/Human Approval is manufactured. Cases,46 apparatus records, original
PDF, receipt, audit, profile and queue remain unchanged. Synthetic fixtures and
monkeypatched authority are test-only, never real engineering evidence.

## Preliminary Pragmatic METAL v0.1 (explicit versioned replay)

`cabinet_sizing.pragmatic_metal_request.v0.1` has exactly
`schema_version, case_id, devices, source_facts`. It accepts no cabinet, interior,
placements, IP claims or installation compatibility. The independently admitted
`pragmatic_source_fact` role binds source dimensions and prior approval separately
to Case/item/apparatus. The scoped WU15 default rehashes the reviewed four-page
source assessment (`8ec1d892...`), its original PDF (`c25dae3b...`) and unchanged
preliminary composition (`218c3dcd...`). It permits only those three raw items or
their expressly accepted name/quantity1 projection, with every component byte
represented in the apparatus hash. A structural projection may rename only the
exact source code/label/quantity fields to builder canonical keys, retaining the
source installation value or explicit unknown. Description, quantity or actual
installation decisions are not normalization and require their own authority.
It does not infer absence for another Case or admit changed apparatus.

`cabinet_sizing.pragmatic_metal.v0.1` reports preserve envelopes, exact source
facts, policy, projected size/row whitelist digest, candidate outcomes, derived
planning layout, independent reserves and required HWD. Only protected
`METAL_SIZES` outer sizes and identity rows enter the whitelist digest; price
fields never enter sizing or its provenance. The selected identity has the exact
`METAL-HXWXD-Drow` form. A missing fit, incomparable/equal minima or any whitelist
drift HOLD. Explicit source HWD validates that exact whitelist size only. A prior
approved cabinet cannot change or shrink without a new direct Human Approval.

Planning enumerates all feasible DIN row counts under the whitelist maximum
height, every relevant last-row envelope height and both vertical/horizontal
arrangements of independent rectangular DIN and panel zones. Width partitioning
is exact within this model, with symmetry, memoization and a bounded search;
exhaustion HOLDs before ranking. Nominal row datums have140mm pitch and are not
physical rail anchors. Every spare row retains the full height/width/depth of an
admitted current apparatus envelope, recorded explicitly; zero-height phantom
capacity is excluded. Unequal occupied-row heights are retained rather than
requiring the tallest envelope on every occupied row. Positive DIN edge/pair
gaps, oversized row envelopes and multiple panel devices are currently unsupported
and HOLD before any claim that a larger size is necessary.

Each planning DIN row contributes its planned length; occupied actual device
width is at most75% of their sum. Independently, panel physical assembly area is
at most75% of its planning rectangle. Neither zone may borrow the other's free
capacity. A single VA88 body151.2 plus two122.5 body-edge clearances requires
396.2mm height, not assembly253 plus245. The101.8mm assembly protrusion must fit
within either body-edge allowance; no symmetric anchor is invented. The assembly
253×93 still determines physical occupied area. Panel reserve may enlarge its
planning rectangle in either axis within each candidate bound. Required dimensions
are rounded upward to six decimal places where division recurs; no round-down.
Outer candidate sizes bound planning extents only, never assert usable interior.

The former default was narrowly enabled for the accepted WU15 Case. Explicit
versioned replay retains these read-only results
from frozen raw apparatus are: ЩО6 required506.4×370.333334×97.8mm, proposed
METAL600×400×250 (row28); НЩР required226.4×320.8×81.5mm and АВР
required224×391.6×81.5mm, each proposed METAL500×400×250 (row22).
These are reproducible preliminary proposals, not factory-layout proofs.
IP, installation compatibility, physical anchors and factory layout remain
explicitly unverified in reports and in the builder's final review before its
approval phrase. The same existing three report/source rechecks apply. No real
approval, Case write, price, commercial document or downstream action is executed.

## Catalogue comparison v0.1 — current automatic default

Every new `size_composition(..., request=None)` uses the expanded METAL/KRN/KRV
comparison. `cabinet_sizing.catalogue_request.v0.1` accepts exactly
`schema_version, case_id, devices, source_facts`; caller cabinet, catalogue and
placements are rejected. The old explicit pragmatic request/report, exact v0.2
request/report and historical v0.1 replay keep their original computation.

`cabinet_catalogue.inventory()` admits the exact governed METAL workbook SHA
`b51d7087e0bd8f92e48985294062ead6826c6b50ce3cfacd0f9d0dc22c05f7f2`.
It verifies the sheet and H/W/D headers, reads only A/E/F/G label/dimension cells,
and inventories all 70 scoped rows: 8–56 METAL (49), 60–72 KRN (13), 73–80 KRV
(8). KURN rows 57–59 and rows 81+ are explicitly outside this family scope.
Each record retains its literal label, qualifier, row, raw dimensional values,
dimension/label cells, path and whole-workbook SHA. A34 says 700×500×200 while
G34 contains `=400`: this record remains UNKNOWN; the formula is never evaluated
or repaired. Named special form factors require separate mounting proof.

The existing active-price resolver verifies the pinned pointer/manifest/workbook
chain, without calculating or reporting money. Its KRN-36 mapping has
H330/W540, while METAL E64/F64 and the label say H540/W330: row 64 remains
UNKNOWN with an explicit identity conflict. Source admission is code-controlled;
JSON approval claims and a caller-supplied SHA cannot admit other sources.
Reparse points, source drift and changed active pointer fail closed.

`cabinet_sizing.catalogue.v0.1` keeps the existing report root keys and full
recomputation gate. A proposed item contains its technical row identity, derived
layout and proof of every compared candidate. A HOLD raises `SizingHold` with
`details`: all 70 `candidate_outcomes` (FIT/NO_FIT/UNKNOWN), reasons, provenance,
`frontier`, apparatus hash and `first_missing`. The CLI includes these details
per item and exits 2 if any item HOLDs. It never selects a cabinet in order to
make an audit-only result look like an automatic proposal.

METAL alone retains the approved outer-bound preliminary planning exception,
using the existing unchanged planner and independent DIN/panel 25% free reserve.
KRN/KRV have no admitted mounting records at present and remain UNKNOWN unless
an independently proven necessary outer bound or explicit source-size constraint
refutes fit. A narrow code-controlled mounting-source registry can admit exact
single-zone DIN row geometry, actual usable rail lengths and installation facts;
it reuses the existing exact DIN layout/reserve helper. Unsupported mounting
geometry remains UNKNOWN. Synthetic records test the mechanics only. Neither
model suffixes nor assumed module pitch establish rows, slots or capacity.

Every UNKNOWN blocks selection unless a necessary constraint proves NO_FIT.
Among proven fits only a unique componentwise minimum may be proposed; equal or
incomparable choices HOLD. No family, volume or financial ranking is applied.
Explicit project HWD validates that size only; prior approved cabinet changes
still require new Human Approval. Physical IP/install/anchors/factory-layout
status remains separate and unverified for the actual WU15 sources.

Technical identities `CATALOGUE-{family}-ROW-{row}` belong only to this new
version. They do not create downstream cost mappings: their report explicitly
states `UNVERIFIED_NEW_TECHNICAL_IDENTITY`, and existing pricing owners retain
their unknown-identity failure. New proposals and HOLDs do not execute Approval1,
change the 46 apparatus records, write a real Case or authorize downstream work.
The builder and confirmed validator consume/recompute this report at the existing
before-phrase, after-phrase and publication boundaries.
# Версионированный METAL source 2026.10.21

Запросы `cabinet_sizing.catalogue_request.v0.2` и отчёты
`cabinet_sizing.catalogue.v0.2` сохраняют точный исторический replay. Поле
`metal_source` содержит конкретную
версию, абсолютный path, SHA256 и predecessor_version из code-controlled registry
`governed_metal_cost.resolve_metal_source`. `CURRENT` разрешается только при
создании запроса; mutable alias в сохранённом binding запрещён. Исторический
`catalogue_request.v0.1` сохраняет GENESIS replay без переинтерпретации.

Принят whole-workbook SHA256
`be4a3497cf86ee4e5a13ac55bfeeeb980e6948cd30847ae027f36d6ca599cc71`:
G34 — literal 200; принятый AutoShape не доказывает mounting, usable geometry,
IP или installation. Все 70 технических записей используют эту версию; прежние
пробелы KRN/KRV, physical installation и Human Approval остаются HOLD.

`resolve_versioned_metal_cost(size, source_version="CURRENT")` — отдельный
read-only API ровно для прежних десяти D22/28/35/42/44/46/51/52/53/54 bindings.
Он вызывает прежний `_inspect_cost` с WU8 identity, не читает B/C sales и не
создаёт D34/new-row mapping. Исторические API, GENESIS, MAIN manifest/selector,
WU8 `metal_cost` и Case pricing chain не мигрированы. Admission источника не
является Case price apply, activation, approval token или Human Approval.

# Технические оси КРН-36 и конструктивное число реек

Новый default — `cabinet_sizing.catalogue_request.v0.3` / `catalogue.v0.3`.
Только эта версия связывает `CATALOGUE-KRN-ROW-64` с В540×Ш330×Г100 мм и
прямым решением Игоря от 2026-10-21: три DIN-рейки. `technical_binding`
содержит точные METAL version/path/SHA и A64/E64/F64/G64, WU8 code path/SHA,
ключ `CAB-KRN-36`, а также решение Игоря. Проверяются точная подпись корпуса,
размеры, WU8 tuple и неизменные legacy identity/fingerprint/source locator.
Отсутствие, смешение или drift этих данных означает HOLD.

Legacy price identity по-прежнему содержит width=540, height=330, depth=100.
Она сохраняется отдельно с `physical_authority=false`: это исторический
ценовой контракт, а не техническое основание физических осей. MAIN mapping,
manifest, pricing owners и остальные 69 записей не переинтерпретируются.
Явные v0.1/v0.2 запросы и отчёты сохраняют прежние записи и axis-conflict.

`rail_count=3` означает только конструктивное число реек. Оно не заполняет
`MOUNTING_SOURCES`, usable geometry, длины, module capacity, IP или installation.
Без независимых источников КРН-36 остаётся UNKNOWN/HOLD. Если позднее
независимый mounting source задаёт другое число реек, сравнение тоже HOLD;
равное число само по себе не доказывает физическую пригодность.
Builder/validator повторно вычисляют v3 на существующих трёх approval boundaries.
Эта техническая привязка не создаёт Case approval, price apply или downstream authority.

# Частичная DIN capacity КРН-36

Текущий default — `cabinet_sizing.catalogue_request.v0.4` / `catalogue.v0.4`.
Явные v0.1/v0.2/v0.3 и pragmatic сохраняют исторические результаты. Новая
версия добавляет только КРН-36 `din_capacity_binding` к неизменной v3 technical
привязке: прямое решение Игоря 2026-10-21, 3 рейки × 12 модулей × 18 мм =
216 мм на рейку и 648 мм суммарно. Это linear capacity, без usable depth,
физических креплений, panel geometry, installation или IP.

`din_capacity_assessment` вычисляется из подтверждённых отдельных аппаратов
Device Envelope v0.2 и их фактических Decimal widths, включая 35.6 мм. DIN
резерв проверяется от общей длины 648 мм: occupied ≤486 мм и каждая row load
≤216 мм. Требования 25% на каждой рейке нет. PANEL аппараты учитываются
отдельно; неизвестные panel geometry/reserve не компенсируются DIN резервом.
Доказанная DIN невозможность даёт NO_FIT даже при неизвестной panel geometry.

Для распределения используется полный `planning.partition` с ограниченным
`Budget`; его reserve lower bound не считается occupied width. В отчёте
сохраняются actual widths каждого unit, occupied/free/reserve denominator и
free percent, фактические row loads и относительные planning row assignments
с pitch 140 мм. Это не заводские координаты. Неизвестные mandatory gaps,
неподдерживаемая геометрия и исчерпанный Budget дают UNKNOWN, а не NO_FIT.
Независимые mounting constraints могут сузить capacity, но не увеличить 216 мм
на рейку. Source/WU8/legacy fingerprint guards v3 повторяются и для v4.

DIN PASS при отсутствии независимого полного mounting evidence сохраняет
overall UNKNOWN, physical installation HOLD и основной `layout=null`.
Полный источник монтажа проверяется отдельно и не выводится из capacity или
внешних размеров. Полный список содержит прежние 70 записей: 49 METAL,
13 KRN, 8 KRV (rows 73–80). Исследование КРВ не дало достаточной admitted
construction authority: их прежние UNKNOWN причины сохраняются, новые
mounting bindings не создаются. Суффиксы моделей и внешние размеры не являются
доказательством числа реек, вместимости или physical fit.

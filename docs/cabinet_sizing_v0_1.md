# Cabinet Sizing v0.1 — automatic contract, Device Envelope v0.2

## QUOTE_PREPARATION v0.5 — отдельный opt-in (решение Игоря 2026-11-04)

Default остаётся `catalogue_request.v0.4` / `catalogue.v0.4`. Исторические
schemas, результаты и требования минимальности не переинтерпретируются.
`cabinet_sizing.catalogue_request.v0.5` содержит ровно прежние v0.4 поля
`schema_version, case_id, devices, source_facts, metal_source` и `quote_choices`:
object `item_id -> exact cabinet_code`. Неизвестные item IDs, поля, пустые коды,
approval flags, caller HWD/placements отклоняются. `metal_source` — конкретная
admitted version, не mutable CURRENT. `quote_request_for` создаёт opt-in запрос.

Система независимо пересчитывает все исходные candidate outcomes и добавляет
каждому `quote_assessment` с `calculation_status` PASS/NO_FIT/HOLD и reasons.
`quote_candidates` содержит только расчётно допустимые exact identities.
Пустой/неполный `quote_choices` позволяет исследовать кандидатов: отсутствующий
выбор даёт `HOLD_QUOTE_CHOICE_REQUIRED` с outcomes и quote_candidates, без выбора
по default/цене/семейству. CLI выдаёт отдельную оценку каждого щита.
Выбор не меняет технические факты и не является Human Approval.

Рекомендация (решение Игоря 2026-11-06, `cabinet_sizing.quote_recommendation.v0.2`):
при `HOLD_QUOTE_CHOICE_REQUIRED` details дополнительно содержат
`quote_recommendation` — один предложенный кандидат, причина (`reason`) и до трёх
альтернатив только из PASS `quote_candidates`. Цель — приблизить подсказку к
выбору инженеров ПТО. Порядок уровней:

1. `DIN_ONLY_MODULAR_BOX` — если щит проходит в модульном боксе КРН/КРВ (на
   практике это только щиты из одних DIN-аппаратов), предлагается наименьший по
   объёму такой бокс;
2. `METAL_FRONT_FILL_MAX_20_PERCENT_DEPTH_MIN_250` — иначе наименьший по фасаду
   В×Ш (затем В, Ш, Г) METAL, у которого планировочные габариты аппаратов
   занимают не более 20% фасада и глубина не меньше 250 мм;
3. `SMALLEST_ELIGIBLE_VOLUME_FALLBACK` — иначе наименьший внешний объём.

В том же решении: в v0.5 quote discovery без reserve policy модульные корпуса
КРН/КРВ проверяются с DIN-резервом 0% (они рассчитаны ровно на число модулей в
названии), как и в существующей family policy `cabinet_reserve.by_family.v0.1`.
Ёмкость каждой рейки и PANEL-правила не меняются; METAL и v0.4 сохраняют 25%.

Глубина 250 мм — стандартная рабочая глубина ПТО. Порог 20% и уровни откалиброваны по одному тестовому Case (выбор ПТО: ЩО-6 →
METAL 800×600×250, заполнение 17.7%; НЩР и АВР → КРН-36) и требуют проверки на
других проектах. `metal_price_available` показывает, есть ли размер в
утверждённых ценах METAL (`wu8_governed_sources.METAL_SIZES`), но на выбор не
влияет. Статус `RECOMMENDATION_ONLY_NOT_A_CHOICE`: рекомендация ничего не
выбирает, HOLD сохраняется, отчёт и provenance не меняются. Выбор по-прежнему
делается только явной записью кода в `quote_choices` после решения Игоря. Если
PASS-кандидатов нет, значение `null`.

Допустим существующий FIT расчётной модели либо узкий DIN capacity-only proof:
strict UNKNOWN вызван только отсутствием physical mounting/depth/install/IP,
DIN capacity PASS, PANEL NOT_APPLICABLE и все units DIN. Исходный UNKNOWN не
переписывается в FIT. Заводской чертёж/Physical FIT не обязательны сами по себе.
Известный NO_FIT, source conflict, unsupported constraints, budget exhaustion,
непроверенная обязательная PANEL-зона или иная неполнота расчёта сохраняют HOLD.
Частичный DIN PASS не является основанием игнорировать PANEL. Пороги family и
более строгие source-bound project requirements применяются как прежде.

Явно выбранный допустимый кандидат не требует доказанной минимальности или
разрешения UNKNOWN других кандидатов. `cabinet_sizing.catalogue.v0.5` сохраняет
прежние root fields `schema_version, case_id, items, sources`; каждый selection
добавляет `engineering_scope=QUOTE_PREPARATION`, `calculation_status=PASS`,
`physical_fit_status=NOT_VERIFIED`, `minimality_status=NOT_VERIFIED`.
DIN capacity layout содержит relative assignments, не заводские координаты.
Exact source HWD и запрет изменения ранее утверждённого корпуса сохраняются.

Перед новой HA1 обязателен прежний `cabinet_sizing.module.v0.1` wrapper с полным
source-bound ledger. v0.5 поддерживает reserve-scoped base и exact recompute,
включая выбор/кандидатов/статусы. Три HA1 rechecks, artifact SHA binding и
no-overwrite не меняются. Review показывает расчётный PASS, NOT_VERIFIED и
необходимость фактического Human Approval; receipt фиксирует состоявшееся
подтверждение точного artifact только для этой стадии. Ни запрос, ни PASS не
создают approval. Источник полномочия — отдельное прямое решение Игоря.

Отдельный bare v0.5 report — только расчётное предложение, не confirmed evidence.
`verify_report` отклоняет его даже вне before-HA1 режима, поэтому обычная
confirmed validation и calculator-input helper не могут обойти ledger.
Штатный новый confirmed-путь требует reserve_base внутри module wrapper.
У capacity-only DIN выбора ledger также не может содержать занятую PANEL/OTHER
зону, включая дополнительные аксессуары с `component_id=null`: одного area
reserve PASS недостаточно для их обязательной расчётной геометрии. Пустые
source-proven non-DIN зоны допустимы; исторические wrappers не меняются.
Для всех v0.5 families non-DIN footprint с дополнительным аксессуаром вне base
geometry также даёт HOLD: module profile доказывает площадь/ownership, но не
содержит H/W/D и проверяемого inclusion binding к base layout. Core PANEL
footprints, уже участвующие в расчётной модели, этим правилом не блокируются.

Мостик к цене (решение Игоря 2026-11-06): `future_case_hardening.ordinary_enclosure_cost`
принимает коды `CATALOGUE-METAL-ROW-N`, `CATALOGUE-KRN-ROW-N`, `CATALOGUE-KRV-ROW-N`.
METAL-строка 8–56 со стандартной подписью `В×Ш×Г ` считается
`governed_metal_cost.resolve_catalogue_metal_cost` из своей строки того же
METAL-прайса, что и Case pricing (GENESIS 2026.06.18), с точной проверкой
формул D/H–N/Q; O/P/S берутся из строки, а для десяти утверждённых размеров
обязаны совпадать с `METAL_SIZES`. Специальные исполнения (подпись с
суффиксом) остаются закрытыми. КРН/КРВ отображаются только на единственный
`CAB-*` из `CABINETS` с той же METAL-строкой (КРН-12…96, КРВ-12…72) и считаются
прежним `cabinet_cost`; КРН-9/КРВ-9/КРН-120+ закрыты. Размеры из подписи
обязаны совпасть с источником. Мостик не меняет `METAL_SIZES`, pragmatic
whitelist и исторические отчёты; согласование цены/срока/КП остаётся отдельным.

Confirmed artifact schema и approval-record schema не меняются. После HA1
существующий следующий шаг — calculator-input draft; verified prices, approvals
цены/срока/КП, send и production остаются отдельными границами. Новый технический
cabinet code не создаёт pricing mapping. Production suitability NOT_VERIFIED:
этот контур не реализует новый производственный gate и не разрешает его обход.

Для новых preliminary-builder HA1 действует отдельный обязательный
`cabinet_sizing.module.v0.1` wrapper и ledger: см.
`docs/mandatory_module_accounting_v0_1.md`. Новая source-bound policy требует
DIN-резерв0% для КРН/КРВ/КУРН и >=10% суммарно для METAL с DIN; modules и mm
проверяются независимо, project requirements могут ужесточать порог. Каждая
рейка ограничена подтверждённой capacity. PANEL остаётся >=25%. КУРН не добавлен
в доступный каталог; неизвестная identity/capacity сохраняет HOLD.
Описанные ниже legacy selector policies и исторические recomputation contracts
не изменены. Новый reserve-scoped base согласует применимые reserve gates без
изменения поиска/ранжирования; исторический 25% replay сохраняется отдельно.

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

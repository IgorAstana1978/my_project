# DINVA classic reusable dynamic quote/invoice renderer v0.2

## Назначение и границы

Контур строит новый XLSX-пакет семейства
`DINVA_CLASSIC_QUOTE_INVOICE_V0_1` по отдельно утверждённому immutable
successor presentation profile v0.2 и отдельно утверждённым business/document
data v0.2. Он не
копирует и не патчит reference workbook, не рассчитывает цену, не выбирает
оборудование и не разрешает отправку клиенту.

Invoice/КП №637 и любое неизвестное семейство не относятся к classic-family:
автоматическая адаптация запрещена, результат проверки — `HOLD`.

## Артефакты управления

- Production v0.2 extractor принимает exact SHA-bound family evidence 463,
  519 и 551, immutable approved presentation profile v0.1 и canonical-logo
  Human Decision с SHA-256
  `e7c043f19b7eb8606f59dd8e7de06b29ca4305cc1fe2362ecb93767dd589f63b`
  как пять доказуемых provenance bindings. Fixed classic blocks и exact logo
  bytes наследуются только из approved v0.1/canonical decision; reusable
  dynamic geometry детерминированно задаётся successor contract и не выводится
  из Invoice519 или старого capacity100 runtime template. Результат всегда
  `DRAFT_PROFILE_CANDIDATE / DRAFT_UNAPPROVED`.
- Future Human Approval presentation profile реализован отдельным
  content-addressed publisher
  `scripts/publish_dinva_classic_presentation_profile_v0_2_approval.py`.
  Его token зависит от exact DRAFT SHA и contract fingerprint; DRAFT producer
  его не принимает и не исполняет.
- Production renderer принимает только
  `IMMUTABLE_APPROVED_PROFILE / APPROVED`, authority
  `IGOR_DIRECT_HUMAN_APPROVAL`, exact profile SHA-256 и approved contract
  fingerprint.
- Document JSON содержит только уже утверждённые данные и цены. Pricing,
  repricing и выбор PN-2/X/G/H находятся вне этого контура.

## Governed document model и №519

Для Invoice519 `terms.payment=null`: C118 запрещает изменение спецификации
после предоплаты, но не определяет самостоятельные условия оплаты. Renderer
показывает exact C116:C123 и approved lead time; отдельный payment не выводит.
Delivery EXW г. Астана сохраняется по C123, lead-time provenance — по C121.

Document contract закрыто хранит ordered `sections`, 88 позиций, source-bound
`apparatus`, отдельные pricing/technical/enclosure approval references,
восемь individual source lines `C116:C123`, утверждённый lead time с отдельным
source/normalization provenance, director/executor text и immutable
document approval provenance. Для approval scope №519 поле `basis` обязано
exact равняться source-bound `project_id = 2024/086`; null/другое значение
означает `HOLD` в publisher, renderer и independent validator. Renderer размещает первый section label в
`section_row`, а последующие labels — в item region перед своей первой
позицией; body/total/bottom рассчитываются динамически, включая более 100
позиций, без fixed profile capacity. Validator независимо повторяет shape, section coverage, source-role,
арифметические, VAT, signature, fingerprint и source-binding gates до проверки
XLSX/OOXML.

Минимальный governed publisher №519 —
`scripts/publish_invoice519_dinva_document.py`. Он принимает exact SHA-bound
commercial pricing ledger, YAUO position-87 Human Decision и canonical Invoice
519 workbook; повторно проверяет все source bindings ledger, значения
`11 963 792 / 7 535 394 / 19 499 186`, отсутствие repricing, 88 source rows,
section ordering, quantities, approved line prices, `400×300×250` для позиции
87, коммерческие условия, `30–40 рабочих дней` и подписи. Missing source mapping
означает `HOLD`; publisher не использует legacy copy-first и не запускает
renderer. Реальный token/output требуют отдельного exact Human Approval.
Approved-mode принимает authoritative approval subject только как exact
`DRAFT_UNAPPROVED` document v0.2 вне Git. Он проверяет supplied/actual DRAFT
SHA, document fingerprint, business invariants и actual SHA всех source
bindings, а затем меняет только approval state. Business document заново из
sources не строится.

Будущий publisher invocation (не является разрешением на запуск):

```powershell
& '.\.venv\Scripts\python.exe' `
  'scripts\publish_invoice519_dinva_document.py' `
  --mode approved `
  --draft-document '<REVIEWED_DRAFT_DOCUMENT_V0_2.json>' `
  --draft-document-sha256 '<EXACT_DRAFT_SHA256>' `
  --output '<NEW_CASE>/invoice519-dinva-document-v0.2-APPROVED.json' `
  --authorization 'IGOR_INVOICE519_DINVA_DOCUMENT_V0_2_APPROVAL_PUBLICATION_AUTHORIZED|DRAFT_SHA256=<EXACT_DRAFT_SHA256>|DOCUMENT_FINGERPRINT=<EXACT_DOCUMENT_FINGERPRINT>'
```

Static legacy token, token другого DRAFT SHA/fingerprint и изменённый после
review DRAFT всегда дают `HOLD`. `client_send_authorized` остаётся `false`.

JSON-контракты:

- `schemas/dinva_classic_presentation_profile_v0_2.schema.json` — reusable
  dynamic successor profile;
- `schemas/dinva_quote_invoice_document_v0_2.schema.json` — source-bound
  successor document с отдельными commercial lines в исходном порядке;
- `schemas/dinva_classic_presentation_profile_v0_1.schema.json`;
- `schemas/dinva_quote_invoice_document_v0_1.schema.json` — исторические v0.1
  контракты, которые successor engine не мутирует и не принимает как v0.2.

## Reusable dynamic layout v0.2

Стабильные family anchors: один client sheet, строки company block 2–6,
title/payer 9–10, header row 15, columns B:I, Times New Roman, A4 portrait,
classic margins, visible gridlines, отсутствие merged cells и exact logo PNG
bytes. Logo задаётся two-cell placement относительно `B2` company block, а не
абсолютной Invoice519 координатой; размещение не пересекает видимый текст.

Позиции и section labels занимают только фактически нужные строки начиная с 16.
`ИТОГО` следует сразу после последней позиции/секции; amount words,
индивидуальные source-bound commercial lines и подписи вычисляются от него без
capacity tail. Колонки C/F/G/I получают bounded content-aware ширину внутри
profile min/preferred/max и общего printable-width limit. Высота каждой строки
детерминированно зависит от font size, ширины, explicit newlines, wrapping и
vertical padding; превышение безопасной Excel height закрывается ошибкой.

Pagination повторяет header row 15, не отделяет section label от первой позиции
и по возможности держит bottom block целиком; manual row breaks вычисляются из
governed page-height budgets. Client sheet не содержит approval IDs, internal
review dates, DRAFT/PASS/no-send сообщений и иных governance lines: они остаются
в JSON/custom OOXML/validator, а `client_send_authorized=false` остаётся CLOSED.
Regression matrix обязана покрывать short, medium, 88/9 Invoice519 shape,
long C/F/G, variable sections/commercial lines и более 100 позиций.

## DRAFT profile candidate

До запуска независимо получить SHA-256 всех пяти sources и проверить, что
новый output case path отсутствует и находится вне Git.

```powershell
& '.\.venv\Scripts\python.exe' `
  'scripts\extract_dinva_classic_presentation_profile_v0_2.py' `
  --family-reference '<INVOICE463.xlsx>' `
  --family-reference-sha256 '<EXACT_463_SHA256>' `
  --family-reference '<INVOICE519.xlsx>' `
  --family-reference-sha256 '<EXACT_519_SHA256>' `
  --family-reference '<INVOICE551.xlsx>' `
  --family-reference-sha256 '<EXACT_551_SHA256>' `
  --approved-v0-1-profile '<IMMUTABLE_APPROVED_V0_1_PROFILE.json>' `
  --approved-v0-1-profile-sha256 '3c3c448c268e2bc87aa9255720e26e7d26fd5f3faa0bd0a42704ad8f69e3f3ca' `
  --canonical-logo-human-decision '<IMMUTABLE_LOGO_DECISION.json>' `
  --canonical-logo-human-decision-sha256 'e7c043f19b7eb8606f59dd8e7de06b29ca4305cc1fe2362ecb93767dd589f63b' `
  --output-profile '<NEW_CASE>/dinva-classic-presentation-profile-v0.2-DRAFT.json'
```

Missing, invalid, substituted или не покрывающий exact 463/519/551 evidence
predecessor/decision означает `HOLD`. Caller-supplied SHA от изменённых bytes,
пусть даже structurally valid, не является approval provenance. Hardcoded
filesystem path не требуется: exact immutable bytes допустимы по другому path,
который записывается в provenance.

Успех означает только deterministic DRAFT candidate. Реальная публикация даже
такого DRAFT profile требует отдельного exact решения Игоря. Успех не разрешает
approval presentation profile, render, изменение Excel, XLSX/PDF, client send
или downstream.

Read-only evidence показал first item rows `16, 16, 17` у трёх family sources.
Это доказывает, что fixed Invoice519/capacity100 geometry нельзя считать
reusable contract. Successor поэтому использует header row 15, dynamic rows,
no capacity tail/no merges и relative two-cell logo placement; Invoice519
остаётся business evidence, а не runtime template.

DRAFT document создаётся тем же publisher с `--mode draft`, новым exact output
`invoice519-dinva-document-v0.2-DRAFT.json` и без `--authorization`. Его
`rendering_authorized=false`; renderer production-mode принимает только
отдельно утверждённый successor document.

## Будущий controlled render

Не запускать для реального кейса без отдельного прямого решения Игоря на exact
approved profile, exact document JSON, exact output и no-overwrite intent.

```powershell
& '.\.venv\Scripts\python.exe' `
  'scripts\render_dinva_classic_quote_invoice.py' `
  --profile '<IMMUTABLE_APPROVED_PROFILE.json>' `
  --profile-sha256 '<EXACT_PROFILE_SHA256>' `
  --document '<APPROVED_DOCUMENT.json>' `
  --document-sha256 '<EXACT_DOCUMENT_SHA256>' `
  --output '<NEW_OUTSIDE_GIT_OUTPUT.xlsx>'
```

Renderer v0.2 проверяет schema-level shape, SHA/family/fingerprint/approval gates,
арифметическое согласование утверждённых сумм, outside-Git/no-overwrite,
создаёт hidden candidate с одним clean sheet и exact именем и геометрией
runtime contract, вызывает независимый validator, повторно читает оба
authoritative input перед atomic hard-link publish и удаляет candidate при
ошибке. Финальный XLSX всегда остаётся с закрытой отправкой клиенту.

## Независимая проверка

```powershell
& '.\.venv\Scripts\python.exe' `
  'scripts\validate_dinva_classic_quote_invoice.py' `
  --workbook '<CANDIDATE.xlsx>' `
  --profile '<IMMUTABLE_APPROVED_PROFILE.json>' `
  --profile-sha256 '<EXACT_PROFILE_SHA256>' `
  --document '<APPROVED_DOCUMENT.json>' `
  --document-sha256 '<EXACT_DOCUMENT_SHA256>'
```

Validator заново открывает workbook и OOXML package, сверяет exact business
cells, dynamic rows, formulas, styles, bounded widths/content-aware heights,
absence of merges, print area/pagination, visible gridlines, asset
bytes/hash/anchor, custom bindings, relationships/content types, запрещённые
parts и calcChain consistency. Неизвестное или непроверяемое состояние — FAIL.

## calcChain

Clean renderer не создаёт `calcChain`. Одновременно должны отсутствовать part,
relationship и content-type residue. Если сторонний candidate содержит
calcChain, validator требует уникальный набор ссылок, в точности равный
фактическим formula cells; stale, duplicate, orphan или missing refs запрещены.

## Human visual review и downstream

### Visual successor v0.3 (DRAFT only)

Second real v0.2 candidate имел technical PASS, но Igor visual REVISE.
Contract недостаточен для C13 (фиксированные 63,75 pt) и border geometry
пустых верхних ячеек. Для logo independent review обнаружил иной proven gap:
renderer терял canonical DrawingML transform и related picture semantics.
Исходный anchor не доказан как root cause overlap. Immutable v0.2 не меняется.

`extract_dinva_classic_presentation_profile_v0_3.py` принимает только exact
approved v0.2 profile SHA и извлекает его actual source bindings повторно.
Border XML всех 104 ячеек `Лист1!B2:I14` должен совпадать во всех 463/519/551;
для canonical 519 SHA `17e31d0312f728800d31fd4f125d285edb1114880500d4833261239b87ab58b5`
это medium perimeter company B2:I6, thin E/F divider, hair separator B7:I7,
medium title/payer B9:I11 и object B12:I14. Это family header evidence,
не fixed runtime template или правило количества позиций Invoice519.

Successor хранит exact border XML/цвета и provenance. C13 использует фактическую
ширину C, font size, word wrapping и явные переводы строк; консервативный предел
ширины glyph 1,1 em, line height 1,5 em, padding 6 pt, Excel ceiling 408 pt.
Переполнение ceiling закрывает render, не обрезает текст. Дополнительная высота
учитывается в first-page budget; индексы body/total/bottom не меняются.
Logo raw bytes и native 200×68 px сохранены. Во всех exact 463/519/551 совпадают
twoCellAnchor markers, editAs=absolute, xfrm off=(457200,285750),
ext=(1504950,514350) EMU, srcRect/stretch, useLocalDpi=0, locks и полный spPr.
Различается только package-local cNvPr id (5287/5265), нормализуемый в 1.
Transform/DPI/extensions не выводятся из markers: successor хранит source-bound
picture XML, а renderer воспроизводит его без потери semantics; independent
validator сравнивает полный expanded-name XML tree, markers и native bytes.
Approved predecessor placement сохраняется без уменьшения. Failed-review DRAFT
SHA `806140a3296d694bf7652cc5e2928e98a627618b3818639ba93d6cbd407868b3`
с shrink workaround остаётся неизменным evidence, не subject для approval.
Synthetic regressions проверяют потерю/изменение transform, crop/stretch, DPI,
locks, hidden geometry и editAs. Native visual acceptance этим не утверждается.
Rich text для `металл 1,2мм` не добавляется.

CLI: `--approved-v0-2-profile <outside-Git exact APPROVED JSON>`
`--approved-v0-2-profile-sha256 <exact SHA> --output-profile <new case>/dinva-classic-presentation-profile-v0.3-DRAFT.json`.
Этот CLI создаёт только DRAFT без overwrite. Existing v0.2 approval publisher
не принимает v0.3 и остаётся неизменным.
Отдельный `scripts/publish_dinva_classic_presentation_profile_v0_3_approval.py`
предоставляет JSON-only capability для exact reviewed SHA
`756a7484827105ece3221241c8caa27e38644e38401636ea305de34d62371ca4` и fingerprint
`2801bcba4a775f870bbf38e72d8a1df6b7fce4969384bb915891add3abbccf32`.
CLI принимает `--draft-profile`, `--draft-profile-sha256`, `--contract-fingerprint`,
`--output`, `--authorization`. Token contract:
`IGOR_DINVA_CLASSIC_PRESENTATION_PROFILE_V0_3_APPROVAL_PUBLICATION_AUTHORIZED|DRAFT_SHA256=<exact>|CONTRACT_FINGERPRINT=<exact>`.
Шесть exact source bindings, включая approved v0.2 predecessor, проверяются
по actual bytes до staging/link и после link. APPROVED — копия reviewed DRAFT;
меняются только artifact_status и пять approval-state fields. Approval ID
содержит DRAFT SHA и fingerprint. Atomic hard-link/no-overwrite и reread gates
сохраняются. Capability не вызывает producer/renderer и не имеет XLSX/PDF/
client-send/downstream действий. Её technical PASS не разрешает real token
execution/publication: перед ними требуется отдельное прямое Human Approval.
Production renderer не принимает DRAFT. Проверки v0.3 render выполняются только
на synthetic inputs с существующим явно включаемым test gate.
Native Excel clipping/visual acceptance остаётся Human review после отдельного
решения на successor approval и новый real XLSX. Ни technical PASS, ни DRAFT
этого решения не заменяют.

После validator PASS Игорь отдельно визуально проверяет pagination, clipping,
качество wrapping, визуальный баланс и client-ready вид. Automated PASS не
является утверждением КП, XLSX/PDF, цены, срока или отправки. PDF generation,
client send, закупка, резерв, оплата, производство, commit и push требуют своих
отдельных решений и этим runbook не разрешаются.

### Native visual successor v0.4 — DRAFT only

Third-real native review отменил visual acceptance v0.3: C13=216 pt оставлял
избыточную пустоту, а C3 терял canonical rich-text formatting. Во всех 463/519/551
исходные 21 пробел C3 имеют Times New Roman bold 20 pt, country text — 16 pt.
Flattening в uniform 16 pt, а не logo DrawingML или смещение сетки, терял отступ.
v0.4 сохраняет exact text и оба source-bound runs; logo PNG, placement, full
DrawingML и 104-cell B2:I14 border map остаются semantic-exact v0.3.
Independent validator проверяет actual OOXML runs и C3-relative physical bounds:
logo right=94,5 pt; минимальный text start=105 pt; gap=10,5 pt. Space advance
0,25 em читается из actual SHA-bound TrueType hmtx/cmap/head, не задаёт новый offset.

C13 повторяет общую 463/519/551 presentation semantics: fixed row 26,1 pt,
Times New Roman bold italic 14 pt, wrap=false, default General/Bottom alignment.
Embedded line breaks сохраняются в exact cell text, но native Excel показывает их
как single-line spill через доказанно пустой corridor C13:H13; I исключён, потому
что несёт right-frame semantics и имеет разную family width. AutoFit и runtime
Excel для C13 запрещены.

Fail-closed fit использует frozen native Excel measurements именно Times New Roman
Bold Italic 14 pt. Метод: AutoFit ширины `M + glyph*20 + M` и
`M + glyph*60 + M`; upper advance = `(width60 - width20 + 0,75 pt)/40`.
Один grid quantum покрывает разность ошибок округления двух измерений. OOXML
column widths C:H переводятся в pixels по maximum digit width Normal Calibri 11
(7 px), затем вычитается стандартный cell padding 5 px.
Источник формулы: [Open XML Column](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.column).
Exact Invoice519 требует conservative upper bound 697,74375 pt при canonical
corridor 804 pt; после 5 px padding available=800,25 pt (margin 102,50625 pt).
Unknown glyph, занятый spill-cell или
превышение corridor дают HOLD; renderer не растит row, не включает wrap и не
использует fallback font. Null object сохраняет fixed family geometry. Body,
total rows и pagination от текста C13 не смещаются.

`scripts/extract_dinva_classic_presentation_profile_v0_4.py` принимает exact
approved v0.3 и SHA-bound native width measurement JSON. Проверяет все шесть
inherited bindings, actual Bold Italic font SHA, canonical C13/C3 agreement,
calibration и повторно читает все sources.
CLI: `--approved-v0-3-profile`, `--approved-v0-3-profile-sha256`,
`--width-measurements`, `--width-measurements-sha256`,
`--country-font-source`, `--country-font-source-sha256`, `--output-profile`.
Output только новый outside-Git/no-overwrite `dinva-classic-presentation-profile-v0.4-DRAFT.json`.
Frozen governed fixture `tests/fixtures/dinva_c13_bold_italic_native_widths.json`
содержит измерения, не шрифт или client XLSX. Measurement helpers/results остаются
внешним analysis evidence. Technical PASS не является native visual acceptance
или разрешением real render.

### Presentation Profile v0.5 approval publisher — capability only

`scripts/publish_dinva_classic_presentation_profile_v0_5_approval.py` принимает
только exact reviewed DRAFT SHA
`bf8ca678c21040e95a0d870a1657324dd42ecc297315135adc67061e7925dbef` и contract
fingerprint `537cf6dfd60b25508b72995b0ec60207a9ce4c99e3a7a14dd8a53358c8b9ccef`.
Он reread-проверяет exact 11 provenance bindings, coherent DRAFT lifecycle и
неизменность contract/fingerprint. APPROVED-копия меняет только artifact status
и пять approval-provenance fields; authority остаётся
`IGOR_DIRECT_HUMAN_APPROVAL`.

Token contract:
`IGOR_DINVA_CLASSIC_PRESENTATION_PROFILE_V0_5_APPROVAL_PUBLICATION_AUTHORIZED|ACTION=IMMUTABLE_APPROVAL_PUBLICATION|DRAFT_SHA256=<exact>|CONTRACT_FINGERPRINT=<exact>|OUTPUT_PATH_SHA256=<sha256-normalized-exact-output-path>`.
Привязка к action и exact output делает token неприменимым к renderer/PDF/client
send/downstream и к альтернативному publication case. Publisher использует новый
outside-Git output, atomic hard-link, repeated source/DRAFT rereads и rollback;
existing case/output либо успешный replay дают HOLD. CLI принимает token только
как внешний input и не создаёт его. Capability PASS не разрешает real token
execution или publication: для exact subject/output нужна отдельная Human Approval.

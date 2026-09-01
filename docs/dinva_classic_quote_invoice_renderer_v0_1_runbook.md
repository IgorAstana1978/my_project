# DINVA classic quote/invoice renderer v0.1

## Назначение и границы

Контур строит новый XLSX-пакет семейства
`DINVA_CLASSIC_QUOTE_INVOICE_V0_1` по отдельно утверждённому immutable
presentation profile и отдельно утверждённым business/document data. Он не
копирует и не патчит reference workbook, не рассчитывает цену, не выбирает
оборудование и не разрешает отправку клиенту.

Invoice/КП №637 и любое неизвестное семейство не относятся к classic-family:
автоматическая адаптация запрещена, результат проверки — `HOLD`.

## Артефакты управления

- Extractor принимает не менее двух classic-family reference XLSX и не менее
  одного certified runtime template XLSX вне Git с exact SHA-256 каждого файла.
  Classic references доказывают принадлежность семейству и общие признаки;
  runtime template является единственным источником exact runtime geometry,
  styles, fixed blocks, formulas, merges, print contract и logo placement.
  Runtime logo bytes принимаются только при exact SHA-256 совпадении с
  consensus logo classic-family references; mismatch означает `HOLD` без
  замены или нормализации asset. Эти роли не взаимозаменяемы. Результат всегда
  `DRAFT_PROFILE_CANDIDATE / DRAFT_UNAPPROVED`.
- Human Approval presentation profile выполняется отдельным будущим процессом,
  которого в v0.1 нет. Нельзя вручную подменять approval-поля.
- Production renderer принимает только
  `IMMUTABLE_APPROVED_PROFILE / APPROVED`, authority
  `IGOR_DIRECT_HUMAN_APPROVAL`, exact profile SHA-256 и approved contract
  fingerprint.
- Document JSON содержит только уже утверждённые данные и цены. Pricing,
  repricing и выбор PN-2/X/G/H находятся вне этого контура.

JSON-контракты:

- `schemas/dinva_classic_presentation_profile_v0_1.schema.json`;
- `schemas/dinva_quote_invoice_document_v0_1.schema.json`.

## DRAFT profile candidate

До запуска независимо получить SHA-256 references и проверить, что output
directory уже существует, находится вне Git, а output-файл отсутствует.

```powershell
& '.\.venv\Scripts\python.exe' `
  'scripts\extract_dinva_classic_presentation_profile.py' `
  --reference '<CLASSIC_REFERENCE_1.xlsx>' `
  --reference-sha256 '<EXACT_SHA256_1>' `
  --reference '<CLASSIC_REFERENCE_2.xlsx>' `
  --reference-sha256 '<EXACT_SHA256_2>' `
  --runtime-template '<CERTIFIED_RUNTIME_TEMPLATE.xlsx>' `
  --runtime-template-sha256 '<EXACT_RUNTIME_TEMPLATE_SHA256>' `
  --output-profile '<NEW_OUTSIDE_GIT_PROFILE.json>'
```

Успех означает только deterministic DRAFT candidate. Он не разрешает render,
публикацию, изменение Excel, PDF или downstream.

Read-only evidence для текущего v0.1 показал first item rows `16, 16, 17` у
трёх classic-family references. Поэтому extractor не угадывает общий item row
из family evidence. Certified runtime template `capacity100_tuned_v4` задаёт
sheet `Счёт-КП шаблон`, header row `15`, section row `16`, first item row `17`,
capacity `100`, exact `31` merged ranges и one-cell logo anchor. При нескольких
runtime templates их канонические contracts должны полностью совпадать, иначе
результат — `HOLD`.

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

Renderer проверяет schema-level shape, SHA/family/fingerprint/approval gates,
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
cells, rows, formulas, styles, widths/heights/merges, print contract, asset
bytes/hash/anchor, custom bindings, relationships/content types, запрещённые
parts и calcChain consistency. Неизвестное или непроверяемое состояние — FAIL.

## calcChain

Clean renderer не создаёт `calcChain`. Одновременно должны отсутствовать part,
relationship и content-type residue. Если сторонний candidate содержит
calcChain, validator требует уникальный набор ссылок, в точности равный
фактическим formula cells; stale, duplicate, orphan или missing refs запрещены.

## Human visual review и downstream

После validator PASS Игорь отдельно визуально проверяет pagination, clipping,
качество wrapping, визуальный баланс и client-ready вид. Automated PASS не
является утверждением КП, XLSX/PDF, цены, срока или отправки. PDF generation,
client send, закупка, резерв, оплата, производство, commit и push требуют своих
отдельных решений и этим runbook не разрешаются.

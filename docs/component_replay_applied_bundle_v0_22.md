# Component replay applied bundle v0.22

## Назначение

`component_replay_applied_bundle.v0.22` — generic non-mutating overlay,
который применяет проверенный `human_decisions_batch.v0.22` к canonical
`component_replay_readiness_bundle.v0.2`.

Overlay не переписывает canonical replay и не является confirmed composition.
Он не разрешает pricing, procurement или production.

## Approval gate до application

Validator `PASS`, exit code `0`, `FROZEN_HUMAN_APPROVAL_DECISIONS`,
`APPROVED_BY_IGOR` и другие approval-поля проверяют claim и структуру artifact,
но не аутентифицируют автора решения и не создают нового Human Approval.

До любого apply Codex показывает Игорю:

- exact resolved path canonical replay и его SHA-256;
- exact resolved path batch JSON и его SHA-256;
- exact resolved output path outside Git;
- overwrite intent: `yes` или `no`.

Apply разрешён только после отдельного прямого решения Игоря для этих exact
inputs, output и overwrite intent. Без такого решения нужно остановиться до
application.

Application `PASS` означает только, что валидный applied overlay записан.
Он не создаёт confirmed composition и не разрешает pricing, КП, закупку или
производство.

## Команды

Application:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\apply_human_decisions_batch_v0_22_to_component_replay.py `
  --canonical-replay <canonical-replay.json> `
  --batch-json <human-decisions-batch-v0.22.json> `
  --output-json <component-replay-applied-bundle-v0.22.json>
```

Независимая проверка:

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\validate_component_replay_applied_bundle_v0_22.py `
  --bundle-json <component-replay-applied-bundle-v0.22.json>
```

Output JSON должен находиться вне Git project. По умолчанию существующий output
не перезаписывается. Явный `--overwrite` разрешает атомарную замену только
outside Git, не обходит outside-Git guard и не меняет входные artifacts.

## Входной контракт

Application принимает:

- canonical replay со schema
  `component_replay_readiness_bundle.v0.2`;
- frozen authority batch со schema `human_decisions_batch.v0.22`;
- путь одного output JSON.

До записи application:

1. читает JSON fail-closed, включая запрет дублирующихся JSON keys;
2. вызывает authoritative
   `scripts/validate_human_decisions_batch_v0_22.py`;
3. проверяет одинаковый `project_id`;
4. вычисляет SHA-256 точных bytes обоих inputs;
5. сверяет SHA canonical replay с `source_bindings` batch;
6. сверяет каждый COMP, position, section, locator и component identity с
   canonical evidence record;
7. строит overlay в памяти и проверяет его независимым validator.

Canonical record сохраняется через:

- `canonical_label`;
- `canonical_document_id`;
- `canonical_source_status`;
- полную `canonical_provenance`.

Новые component/evidence IDs не создаются.

## Output schema

Корень содержит только:

- `schema_version = component_replay_applied_bundle.v0.22`;
- `project_id`;
- `application_status = APPLIED`;
- `authority = IGOR_DIRECT_HUMAN_APPROVAL`;
- `source_lineage`;
- `direct_component_quantities`;
- `cabinet_level_aggregates`;
- `scope_exclusions`;
- пересчитанный `coverage`;
- `confirmed_composition_created = false`;
- `pricing_started = false`;
- `downstream_started = false`.

`source_lineage` фиксирует SHA-256 и schema version canonical replay и batch,
а также строго требует `batch_id = "022"` и `prior_batch_id = "021"`.

## Decision projections

### DIRECT_COMPONENT_QUANTITY

`quantity_per_cabinet` — положительное целое значение decision. Оно относится
только к exact COMP membership этой decision.

### CABINET_LEVEL_AGGREGATE

`aggregate_quantity_per_cabinet` хранится один раз на decision:

- `applies_once_per_cabinet = true`;
- `multiply_by_member_count = false`;
- members являются только evidence coverage;
- aggregate quantity не копируется в members.

### SCOPE_EXCLUSION

Projection сохраняет identity, members, provenance, `scope_status`,
`future_inclusion_requires` и `prohibited_downstream`.

Quantity отсутствует. Excluded record нельзя включать в installed composition,
pricing, procurement или production.

## Unresolved metadata

`model_type = null` и `poles = null` сохраняются без вывода из названия,
аналогии, ratings или соседних records. Application не придумывает model,
poles, row-to-pole mapping или quantity.

## Coverage и fail-closed правила

Validator пересчитывает:

- `direct_component_count`;
- `aggregate_member_count`;
- `exclusion_component_count`;
- `union_component_count`.

Отклоняются:

- дублирующиеся JSON keys на любом уровне до contract validation;
- неизвестные или лишние поля;
- неверные schema/status/authority/source lineage;
- `batch_id`, отличный от `"022"`, или `prior_batch_id`, отличный от `"021"`;
- SHA не в формате 64 lowercase hex;
- quantity `0` и неположительные direct/aggregate quantities;
- quantity у exclusions;
- дубли decision ID/code или COMP;
- пересечения COMP между decisions;
- aggregate, размножаемый по members;
- declared coverage, не совпадающий с содержимым;
- любой downstream flag со значением `true`.

Contract generic: он не содержит project-specific COMP, SHA или ожидаемых
counts.

## Deterministic и atomic write

JSON сериализуется с отсортированными keys, UTF-8 и одним завершающим LF.
Сначала полностью записывается временный файл в каталоге output, затем output
создаётся атомарно. При ошибке временный файл удаляется, новый output не
остаётся.

## Approval boundary

Applied overlay сам по себе не создаёт confirmed composition. Следующие шаги
требуют отдельного Human Approval и отдельного contract/application path.

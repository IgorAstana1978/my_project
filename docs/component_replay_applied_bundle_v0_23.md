# Component replay applied bundle v0.23

## Назначение

`component_replay_applied_bundle.v0.23` — generic applied overlay для цепочки:

```text
component_replay_readiness_bundle.v0.2
  + human_decisions_batch.v0.22
  + human_decisions_batch.v0.23
```

Application сохраняет canonical evidence, применяет frozen v0.22 decision
semantics как base layer и затем записывает bounded v0.23 corrections,
reconfirmations и reserved-space requirements.

Bundle не является confirmed composition и не разрешает pricing, procurement,
production или client send.

## Approval gate

Validator `PASS`, exit code `0`, frozen/approved/application statuses и SHA
bindings проверяют contract claims, но не создают Human Approval.

Перед реальным apply Игорь отдельно подтверждает:

- exact resolved canonical replay path и SHA-256;
- exact resolved prior v0.22 path и SHA-256;
- exact resolved correction v0.23 path и SHA-256;
- exact resolved output path вне Git;
- overwrite intent: `yes` или `no`.

Без такого exact решения application не запускается.

## CLI

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\apply_human_decisions_batch_v0_23_to_component_replay.py `
  --canonical-replay <component-replay-readiness-bundle.json> `
  --prior-batch-json <human-decisions-batch-v0.22.json> `
  --correction-batch-json <human-decisions-batch-v0.23.json> `
  --output-json <component-replay-applied-bundle-v0.23.json>
```

Опциональный `--overwrite` разрешает только атомарную замену существующего
output вне Git. Он никогда не обходит outside-Git guard и не разрешает output,
совпадающий после path resolution с одним из трёх input artifacts.

## Входная validation

До записи script:

1. читает три JSON с duplicate-key guard;
2. валидирует canonical record contract штатным canonical guard существующего
   v0.22 application path;
3. вызывает `validate_human_decisions_batch_v0_22.py`;
4. вызывает `validate_human_decisions_batch_v0_23.py`;
5. требует одинаковый `project_id`;
6. вычисляет SHA-256 exact bytes трёх inputs;
7. проверяет binding canonical SHA в v0.22;
8. проверяет binding canonical и prior-v0.22 SHA в v0.23;
9. сопоставляет каждый v0.23 item по exact COMP, section, position, locator,
   provenance и prior member;
10. проверяет original signature correction против exact v0.22 decision;
11. проверяет canonical identity для approved correction, reconfirmation и
    reserved-space identity.

Canonical readiness validator, который восстанавливает bundle из intake
manifest, имеет отдельный двухфайловый interface. Новый CLI не принимает intake
manifest и поэтому использует тот же canonical input guard, что существующий
v0.22 application path; full readiness artifact должен быть frozen и отдельно
validated до Human Approval на application.

## Application order

`application_order` фиксирован:

1. `human_decisions_batch.v0.22`;
2. `human_decisions_batch.v0.23`.

v0.22 decisions проецируются с прежней семантикой:

- `DIRECT_COMPONENT_QUANTITY`;
- `CABINET_LEVEL_AGGREGATE`;
- `SCOPE_EXCLUSION`.

Identity mismatch v0.22 против canonical разрешён только тогда, когда exact
COMP имеет `COMPONENT_SIGNATURE_CORRECTION` в v0.23 и его
`original_signature` буквально совпадает с проекцией v0.22 signature.
Непокрытый mismatch отклоняется fail-closed.

Каждый COMP из v0.22 до проекции явно проверяется на присутствие в canonical
replay. Unknown prior-only COMP отклоняется controlled application error.

## Output schema

Корень содержит только:

- `schema_version = component_replay_applied_bundle.v0.23`;
- `project_id`;
- `application_status = APPLIED`;
- `authority = IGOR_DIRECT_HUMAN_APPROVAL`;
- `application_order`;
- `source_lineage`;
- `canonical_component_evidence_records`;
- `prior_v0_22_application`;
- `component_signature_overlays`;
- `reserved_meter_space_requirements`;
- `coverage`;
- `confirmed_composition_created = false`;
- `pricing_started = false`;
- `downstream_started = false`.

`source_lineage` фиксирует exact SHA-256, schema versions и batch IDs всех
трёх inputs.

`canonical_component_evidence_records` — полная неизменённая копия
`identified_component_evidence_records` canonical replay. Ни один v0.23 item
не переписывает эти records. COMP, отсутствующие в v0.23, остаются только в
этом canonical layer и не получают overlay.

## v0.23 overlay

### COMPONENT_SIGNATURE_CORRECTION

Записывается отдельный overlay:

- canonical COMP/position/section/locator;
- `original_signature`;
- `approved_signature`;
- `quantity_per_cabinet`;
- provenance и correction reason;
- `canonical_evidence_modified = false`;
- `application_status = APPLIED`.

Approved signature не заменяет и не удаляет canonical evidence.

### COMPONENT_RECONFIRMATION

Записывается отдельный overlay с теми же полями. Original и approved signatures
равны по frozen v0.23 contract. Canonical evidence остаётся неизменённым.

### RESERVED_METER_SPACE

Записывается только в `reserved_meter_space_requirements`:

- `reserved_space_per_cabinet = 1`;
- `installed_component = false`;
- `meter_connection = THREE_PHASE_DIRECT`;
- `future_inclusion_requires =
  SEPARATE_METER_SELECTION_AND_IGOR_APPROVAL`;
- downstream boundary;
- `canonical_evidence_modified = false`.

Requirement не входит в component overlays и не становится установленным
счётчиком.

## Coverage

Application пересчитывает:

- canonical component count;
- четыре v0.22 coverage counts;
- correction count;
- reconfirmation count;
- reserved-space count;
- union v0.23 overlay component count.

Duplicate COMP, неизвестный COMP или расхождение declared/actual coverage
отклоняются.

## Write safety

Output разрешён только вне Git project. Проверка выполняется после
`resolve(strict=False)`, поэтому `--overwrite` её не обходит. Resolved output
должен отличаться от resolved canonical replay, prior v0.22 и correction v0.23.

JSON детерминированно сериализуется в UTF-8 с одним завершающим LF. Запись:

1. создаёт temporary file в output directory;
2. полностью записывает и `fsync`-ит bytes;
3. атомарно создаёт новый output или заменяет его при explicit `--overwrite`;
4. удаляет temporary file при любой ошибке.

При fail до новой записи output не создаётся. Существующий output без
`--overwrite` сохраняется без изменений.

## Boundary

Applied bundle подтверждает только выполненную technical projection. Он не
создаёт confirmed composition и не разрешает pricing, КП, закупку,
производство или отправку клиенту. Каждый следующий этап требует отдельного
contract и отдельного решения Игоря.

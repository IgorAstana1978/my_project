# Human decisions batch v0.23

## Назначение

`human_decisions_batch.v0.23` — generic frozen Human Approval contract для:

- bounded correction технической component signature;
- повторного подтверждения уже корректной signature;
- требования зарезервированного места под трёхфазный счётчик без
  установленного счётчика.

Artifact не применяет решения и не создаёт confirmed composition, pricing,
procurement или production authorization.

## Root contract

Обязательные значения:

```text
schema_version: human_decisions_batch.v0.23
compatible_with: human_decisions_batch.v0.22
batch_id: "023"
prior_batch_id: "022"
artifact_status: FROZEN_HUMAN_APPROVAL_CORRECTIONS
authority: IGOR_DIRECT_HUMAN_APPROVAL
application_status: NOT_EXECUTED
confirmed_composition_created: false
pricing_started: false
downstream_started: false
```

Root также содержит непустые `case_id`, `project_id`, exact
`source_bindings` и непустой `cabinet_records`.

`source_bindings` содержит только:

- `canonical_bundle_sha256`;
- `prior_batch_sha256`.

Оба значения — 64 lowercase hexadecimal characters.

## Cabinet records

Каждый cabinet record содержит только:

```text
cabinet_record_id
cabinet_template
position_id
section
source_locator
items
```

Cabinet IDs уникальны во всём artifact. `items` — непустой список. Item IDs и
COMP IDs также глобально уникальны: один COMP не может входить в два cabinet
records или два decisions.

## Provenance

Каждый item содержит exact непустой provenance object:

```text
source_artifact_sha256
source_record_id
source_locator
```

SHA имеет формат 64 lowercase hex; остальные поля — непустые строки.
`source_artifact_sha256` обязан точно совпадать либо с
`source_bindings.canonical_bundle_sha256`, либо с
`source_bindings.prior_batch_sha256`.

## Signature

`original_signature` и `approved_signature` содержат только:

```text
component_identity
model_type
ratings
poles
functional_role
```

`model_type` и `poles` могут быть `null`. Validator не выводит отсутствующие
значения из identity, ratings или аналогии. Ratings — список уникальных
непустых строк; poles, когда задан, является positive integer.

## Item kinds

### COMPONENT_SIGNATURE_CORRECTION

Содержит:

```text
item_id
item_kind
component_evidence_id
original_signature
approved_signature
quantity_per_cabinet
provenance
correction_reason
application_status
```

`original_signature` и `approved_signature` обязаны различаться.
`quantity_per_cabinet` — positive integer.
`application_status` остаётся `NOT_EXECUTED`.

### COMPONENT_RECONFIRMATION

Имеет тот же exact набор полей. Обе signatures обязаны быть полностью равны.
`correction_reason` фиксирует основание повторного authority confirmation, но
не меняет signature. Quantity остаётся positive integer.

### RESERVED_METER_SPACE

Содержит только:

```text
item_id
item_kind
component_evidence_id
requirement_kind
meter_connection
reserved_space_per_cabinet
installed_component
original_identity
provenance
future_inclusion_requires
prohibited_downstream
application_status
```

Обязательные значения:

```text
item_kind: RESERVED_METER_SPACE
requirement_kind: RESERVED_METER_SPACE
meter_connection: THREE_PHASE_DIRECT
installed_component: false
application_status: NOT_EXECUTED
```

`reserved_space_per_cabinet` строго равен `1`. В одном `cabinet_record`
разрешён не более чем один `RESERVED_METER_SPACE`. Component quantity,
`original_signature` и `approved_signature` запрещены.

`future_inclusion_requires` строго равен:

```text
SEPARATE_METER_SELECTION_AND_IGOR_APPROVAL
```

`prohibited_downstream` содержит ровно:

- `installed_composition`;
- `pricing`;
- `procurement`;
- `production`.

Зарезервированное место не является установленным счётчиком и не разрешает
автоматически выбирать или добавлять модель счётчика.

## Fail-closed validation

Validator отклоняет:

- duplicate JSON keys до contract validation;
- неизвестные, пропущенные и лишние поля;
- неверные root constants или SHA format;
- пустые cabinet/item collections;
- duplicate cabinet IDs, item IDs или COMP IDs;
- неизвестный item kind;
- quantity `0`, отрицательные, fractional или Boolean quantities;
- correction с одинаковыми signatures;
- reconfirmation с различающимися signatures;
- reserved space с component quantity или approved component signature;
- `reserved_space_per_cabinet`, отличный от `1`;
- более одного reserved meter space в одном cabinet record;
- `installed_component: true`;
- пустой или malformed provenance;
- provenance SHA, не связанный с одним из двух root source bindings;
- неверный `future_inclusion_requires`;
- неверный reserved-space downstream boundary;
- любой executed/downstream root или item status.

Contract generic. Он не содержит project-specific COMP, TFE, section, SHA,
cabinet count или item count.

## Validator

```powershell
.\.venv\Scripts\python.exe `
  .\scripts\validate_human_decisions_batch_v0_23.py `
  --batch-json <human-decisions-batch-v0.23.json>
```

PASS означает только соответствие frozen unexecuted contract. Применение
batch, создание replay overlay и любой downstream требуют отдельных contracts
и отдельного Human Approval.

# Mandatory Module Accounting v0.1

Новые запуски preliminary builder перед HA1 требуют отдельный
`cabinet_sizing.module.v0.1`. Старые evidence records, sizing reports и
confirmed artifacts не мигрируются. Approval phrase, authority, decision record,
artifact hash binding, publication/no-overwrite и реальные registry entries не
меняются. Полный монтажный BOM, подбор SKU и выбор корпуса вне этого контракта.

## Политика

- КРН/КРВ/КУРН: DIN-резерв 0%; допускается 100% подтверждённой вместимости.
- METAL с DIN: минимум 10% свободно **суммарно по щиту**, независимо для nominal
  modules и реальных миллиметров. Каждая рейка обязана вмещать назначенные footprint;
  отдельного процента свободного места на каждой рейке нет.
- `project_min_din_free_percent` может только ужесточить порог семейства.
- PANEL: не менее 25% свободной площади в каждой PANEL-зоне;
  `project_min_panel_free_percent` может только ужесточить 25%.
- OTHER: отдельная зона с независимой проверкой площади/вместимости, без
  заимствования DIN или PANEL ресурса.
- Module PASS не устанавливает physical FIT, монтажную глубину, тепловую
  пригодность, коммутацию или полноту монтажного BOM.

Прямое решение Игоря от 2026-11-03: `cabinet_reserve.by_family.v0.1`.
Применимые reserve checks base sizing и ledger используют одну policy. Поиск,
геометрические ограничения, budgets, сравнение минимумов и ranking не изменены.
Исторические вызовы без новой policy сохраняют прежние 25% и прежние reports;
их operation order не переинтерпретируется.

Тип проверяется через exact governed identity либо свежую source-bound запись
каталога с совпадающими code/type/HWD, не по label или похожему названию.
Неизвестная/противоречивая identity даёт HOLD. Правило 0% для КУРН не вводит его
в доступный каталог: production RANGES по-прежнему исключает КУРН. Capacity,
количество и полезная длина реек остаются отдельными source facts. Module PASS
при 100% линейной занятости не устанавливает physical FIT.

## Источники и authority

Новый отдельный документ `module_accounting.evidence.v0.1` читается существующим
`cabinet_sizing_evidence.read(binding, "module_accounting")`. Binding ровно
`{path, sha256}`. Роль/path/SHA должны быть отдельно admitted существующим
code-controlled registry. Этот change **не добавляет реальных admissions**.
SHA, JSON flags, test fixtures и PASS не создают Human authority.

Все raw files должны присутствовать локально: absolute path, no reparse,
size limit, SHA, strict UTF-8 и duplicate-key checks сохраняются. Sources и
применимые revisions перечитываются при каждом recompute. В каждом техническом
record `source` имеет ровно `{path, sha256, locator}` и ссылается на один из
root `raw_sources`. URL-only или свободный label не доказывает модули/ширину.

### Exact root fields

```text
schema_version = module_accounting.evidence.v0.1
case_id
composition_sha256
sizing_sha256
inventory_scope = ALL_INSTALLED_EQUIPMENT_AND_DIN_ACCESSORIES
products
profiles
boards
raw_sources
```

`composition_sha256 = composition_hash(items)` связывает ordered apparatus hashes
и exact выбранные cabinet objects. `sizing_sha256` связывает **весь** base sizing
report. Это контроль данных, не источник разрешения выбора/замены. Количество
щитов положительное целое и фиксируется в каждом board: ledger описывает одну
сборку данного item, не складывает несколько корпусов в одну рейку.

### Products

Каждый product содержит ровно:

```text
id manufacturer sku revision mounting nominal_modules width_mm area_mm2 source
```

`mounting`: DIN, PANEL или OTHER. Нет whitelist по назначению аппарата: MCB,
RCBO, RCD, РН-47, реле, контакторы, выключатели нагрузки, таймеры, индикаторы и
новые виды проходят одинаковую проверку exact источника. Пустые/UNKNOWN/TBD
SKU/revision недопустимы.

Для DIN обязательны положительные source-proven `nominal_modules` и `width_mm`;
`area_mm2=null`. Дробные значения допускаются только как явный факт источника,
с существующими Decimal/range/precision limits. Boolean, NaN и infinity
недопустимы. Для PANEL/OTHER modules и width строго null, а area положительна.
Здесь null означает **неприменимый DIN measure**, не неизвестный DIN footprint.
Для DIN-аксессуара без доказанных необходимых полей получается HOLD, а не 0.
Положительное module count не выводится из полюсов, install_type или ceil(width/18).

### Совместно устанавливаемые footprint profiles

Каждый profile содержит ровно:

```text
id product_ids nominal_modules width_mm area_mm2
left_gap_mm right_gap_mm allowed_zones source
```

`product_ids` — точный ordered список изделий одной монтажной зоны, с повторами
для нескольких экземпляров одного SKU. Смешение DIN и
PANEL/OTHER в одном footprint запрещено. Для singleton profile размеры/модули
обязаны совпадать с product. Для совместного footprint источник явно доказывает
комплект, общую ширину/модули/площадь и inclusion аксессуаров. Это конфигурация
монтажа реальных SKU, не фиктивная модель из независимых MAX разных аппаратов.

Профиль применяется к explicit экземплярам ровно один раз. Нельзя одновременно
учесть аксессуар в общем footprint и повторно отдельной группой. Все products
проверяются по источникам даже при совместном footprint. Обязательные left/right
gaps входят в миллиметровую занятость; неподдерживаемое дополнительное поле
ограничения отклоняется strict schema. `allowed_zones` задаёт допустимые exact
zone IDs; совместная группа занимает непрерывный footprint одной рейки/зоны.

### Boards, instances, groups и zones

Board:

```text
item_id cabinet_sha256 quantity
project_min_din_free_percent project_min_panel_free_percent
zones instances groups source
```

`cabinet_sha256=digest(item.cabinet)`; ordered item coverage и quantities
проверяются. Неизвестное project requirement не следует представлять как 0:
значение 0 допустимо лишь как отдельно source-bound факт отсутствия более
строгого требования; технические факты admitted document подлежат review.

Instance:

```text
id component_id unit product_id
```

Для каждого component требуется ровно один instance на каждую unit quantity.
Один ID не может дублироваться внутри board. Дополнительные установленные
аксессуары имеют собственный instance ID, `component_id=null, unit=1`, exact
product source и входят в обязательное footprint coverage. Этот inventory не
добавляет аксессуары в Case и не утверждает полный монтажный BOM. Его scoped
полнота — технический source claim, которому нужен exact source admission.

Group:

```text
id profile_id instance_ids zone_id
```

Точное ordered соответствие profile, все instances назначены ровно один раз,
совместимые mounting kind и allowed zone обязательны. Unit quantities, covered
instances и shared footprint ownership не заменяются суммой количества строк.

Zone (одна DIN-рейка либо отдельная PANEL/OTHER область):

```text
id kind capacity_modules capacity_mm capacity_area_mm2 source
```

Для DIN modules и mm положительны и независимы; area null. Для прочих зон
modules/mm null, area положительна. Capacity не выводится из suffix корпуса,
наружной ширины или ширины панели. Каждая DIN-рейка отдельно проверяется на
перегрузку обоих measures; затем проверяется суммарный reserve. Для PANEL
сохраняется independent area reserve. Неиспользуемые дополнительные zones тоже
нуждаются в доказанной capacity; фантомные рейки не создаются.

## Ledger и интеграция

`build_ledger(case_id, items, base_report, binding)` возвращает отдельный
`module_accounting.ledger.v0.1`: case/composition/base hashes, `evidence_binding`,
instances, footprint ownership, occupied/free по каждой зоне и суммарные reserves.
Результат не содержит approvals или обещания physical FIT.

`build_sizing_report` оборачивает base report в strict
`cabinet_sizing.module.v0.1` с exact root fields:

```text
schema_version case_id items sources base_report module_ledger
```

`sources` ровно `{base_sizing_sources, module_evidence}`. Обёртка не является
новым selector request; base selector не получает ни нового SKU, ни caller choice.
`verify_sizing_report` заново проверяет historical base существующим verifier и
полностью пересчитывает ledger. Подмена любого поля, источника или количества
делает recomputation неравным/HOLD. Вложенные wrappers запрещены.

Новые module-backed запуски вызывают `size_base`: admitted module evidence
перечитывается до расчёта, чтобы source-bound project requirements применялись
уже в base reserve gates. Результат имеет отдельный schema
`cabinet_sizing.reserve_base.v0.1` и strict sources ровно
`{request, reserve_policy, algorithm_schema}`. Policy содержит version, Case ID
и явные project DIN/PANEL requirements по item. Внешний module evidence binding
не входит в base hash, исключая циклическую SHA-зависимость; полный wrapper и
ledger связывают и перечитывают его отдельно. Sizing/composition hashes в
evidence связывают окончательный reserve-scoped результат, как и прежде.

Recompute сравнивает policy с заново прочитанным admitted module source, затем
полностью повторяет прежний sizing с теми же reserve-параметрами и проверяет
exact cabinets. Отдельные legacy base reports с прежними schemas сохраняют
прежний replay. При отсутствии module evidence legacy preflight может выявить
свой первый blocker, но новая HA1 в любом случае остаётся HOLD без ledger.

Builder принимает `--module-evidence-json` и `--module-evidence-sha256` вместе.
Отсутствие источника даёт HOLD до approval phrase. После штатного base sizing
и присвоения его exact cabinet objects строится wrapper. Новая
`cabinet_sizing.verify_before_ha1` требует wrapper, затем выполняет все проверки.
Эта функция используется builder до phrase, после phrase и в его существующем
publication recheck. Нет нового approval action или изменений approval record.

Confirmed artifact использует **прежнюю** структуру v0.1, но с versioned sizing
report в уже существующем поле `cabinet_sizing`. Strict component/device schemas
не ослаблены. `validate_confirmed_composition_artifact(...,
before_human_approval_1=True)` требует module wrapper. Обычная read-only проверка
legacy artifacts без new-HA1 режима продолжает работать; low-level
`verify_report` сохраняет historical recomputation. Это не право провести новую
HA1 без ledger. Historical applied v0.23/v0.2 replay остаётся отдельным прежним
контрактом; module CLI options с ним смешивать нельзя.

## Проверки

Targeted tests используют только TEST источники и scoped monkeypatch admission.
Старые workflow fixtures снабжают старые сценарии **валидируемыми** synthetic
module sources, а не отключают gate. Отдельные integration tests восстанавливают
native helper и доказывают HOLD без module input, source drift до phrase,
после phrase и на publication recheck; отдельно доказываются пороги семейства,
100% source capacity, METAL 10% и неизменные PANEL 25%.
Real Case/admissions/approval-token execution в тестах отсутствуют.

Для core instances wrapper также перечитывает существующее base device evidence:
mounting kind должен совпадать, exact ширина/площадь продукта не может превышать
соответствующий консервативный base envelope. Противоречие даёт
`HOLD_MODULE_BASE_MOUNTING_CONFLICT` либо
`HOLD_MODULE_BASE_FOOTPRINT_UNDERBOUND`, без смены корпуса или SKU. Совместные
аксессуарные footprints учитываются отдельным источниковым профилем целиком.

Арифметика ledger выполняется в отдельном Decimal Context с precision50,
независимым от округления/traps вызывающего кода. Ограничения source precision,
range и collection count сохраняют точность acceptance comparisons. Recurring
division используется только для отображения процента; pass/fail определяется
точным сравнением произведений, без округления процента до границы.

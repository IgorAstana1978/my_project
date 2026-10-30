# DINVA METAL Mounting Panel v0.1

Прямое Human Approval Игоря от 2026-10-30:
`IGOR-DINVA-METAL-MOUNTING-PANEL-20261030`.

Для **стандартного DINVA METAL с наружной дверью и монтажной панелью**:

- Hпанели = Hкорпуса − 100 мм;
- Wпанели = Wкорпуса − 80 мм.

Входные оси — наружные В×Ш×Г в мм, выходные — В×Ш панели в мм.
Глубина не вычисляется и не наследуется от наружной глубины.

| Корпус В×Ш×Г, мм | Панель В×Ш, мм |
|---|---|
| 800×600×250 | 700×520 |
| 1000×600×250 | 900×520 |
| 600×400×250 | 500×320 |

## Read-only API и интеграция

`scripts/dinva_metal_mounting_panel.py` использует существующие публичные
`cabinet_catalogue.inventory` и `cabinet_sizing_evidence.read/safe_bytes`.
Это отдельный opt-in расчёт; production selectors, v0.1/v0.2 layout, Case,
наружные размеры и исторический replay не изменяются.

`panel_hw_mm([800, 600, 250]) == [700, 520]` воспроизводит только условную
арифметику. Этот helper не определяет исполнение и не создаёт source evidence.
Он принимает только три положительных целых размера; неположительная панель
означает `SizingHold`.

`assess_panel(cabinet_code, construction_binding=None,
source_version="2026.10.21")` заново читает pinned каталог, сохраняет точные
label/family/row/HWD/path/SHA/cells и provenance формулы. Mutable `CURRENT`
не допускается. КРН/КРВ и другие семейства, специальные/неподтверждённые
записи получают HOLD без размера панели. Пустой qualifier и literal HWD сами
по себе **не подтверждают** стандартное исполнение, дверь и панель.

Для применения требуется отдельно admitted источник роли
`metal_standard_construction` через существующий code-controlled
`cabinet_sizing_evidence.AUTHORIZED`. Реальных источников этой роли сейчас
нет; формула не расширяет registry. Поэтому реальные записи каталога до
получения construction evidence остаются HOLD. Caller SHA, approval-флаги
JSON и статус тестов не создают admission или нового Human Approval.

Контракт admitted JSON содержит ровно:

- `schema_version = dinva_metal.standard_construction.v0.1`;
- `catalogue_identity`: точные поля `IDENTITY_FIELDS` из текущей записи;
- `execution = STANDARD_OUTER_DOOR_WITH_MOUNTING_PANEL`;
- непустой `raw_sources`: исходные path/SHA bindings, перечитываемые существующим
  evidence reader, вместе с проверками absolute path/reparse/SHA/duplicate keys.

При совпадении всех привязок результат имеет
`status=PANEL_DIMENSIONS_BY_APPROVED_RULE` и `panel_hw_mm`.
Источники каталога и исполнения повторно читаются до возврата результата.
`verify_assessment(report)` независимо перечитывает источники и полностью
пересчитывает отчёт; подмена provenance, размеров или identity даёт HOLD.
Malformed/unadmitted/drifted evidence также вызывает `SizingHold`.

## Сохранённые границы и историческое свидетельство

Размер панели не доказывает usable geometry, полезную глубину, крепления,
анкеры, зазоры, reserve, wiring, IP/installation или physical FIT.
`usable_geometry_status=UNKNOWN`, `usable_depth_status=UNKNOWN`,
`physical_status=HOLD`, остановка перед `HUMAN_APPROVAL_1` сохраняются даже
при успешном вычислении панели. Размер не передаётся в packing как usable box.
Human Approval технического состава, размеров корпуса и downstream остаются
отдельными gates согласно `docs/cabinet_sizing_v0_1.md`.

Исторические **720×520 мм** сохраняются как отдельное свидетельство:
`tests/test_engineering_layout_v02.py::test_reported_side_panel_connection_and_keepout_regression`
использует сценарную границу `[720, 520, 200]`. Этот fixture не изменён;
его глубина 200 мм остаётся сценарной. Он не подтверждает заводскую геометрию
и не является результатом новой формулы для корпуса 800×600×250 мм.
Новая формула даёт для такого стандартного корпуса **700×520 мм**;
исторические данные не пересчитываются и не перезаписываются.

Regression tests включают три утверждённых примера, fail-closed family и
construction admission, source/provenance drift и независимость physical HOLD.
Синтетические источники в tests проверяют только механику допуска.

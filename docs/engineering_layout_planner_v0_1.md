# Engineering Layout Planner v0.1

Отдельный read-only слой исследует совместную компоновку по исходной
аппаратуре и профилям параметров. Он сохраняет все 70 записей каталога для
каждого щита, исходный strict/advisory отчёт и его SHA. Корпус не назначается,
цены не читаются новым кодом, Case и BOM не изменяются. Итоговые `real_status`
и `physical_status` всегда `HOLD`, остановка — перед `HUMAN_APPROVAL_1`.
Новая схема не допускается прежним strict verifier, в том числе перед A1.

## Публичные интерфейсы

`assess_composition(case_id, items, scenarios=None, strict_request=None)` строит
`engineering_layout.assessment.v0.1`. `verify_assessment(report, items,
expected_case_id=...)` заново читает источники и пересчитывает весь результат.
`format_assessment(...)` возвращает проверенный Markdown со всеми исходными
ограничениями и геометрией. `render_witness_svg(..., item_id=...,
cabinet_code=..., scenario_id=...)` выбирает только вид уже вычисленного
witness после повторной проверки. Выбор вида не влияет на оценки кандидатов.

CLI `scripts/engineering_layout_planner.py` принимает обязательные
`--case-id`, `--composition-json` и необязательные пары
`--request-json/--request-sha256`, `--scenarios-json/--scenarios-sha256`.
`--format json|markdown` управляет только stdout; файловых writes нет.
И валидный исследовательский HOLD, и ошибочный ввод дают exit 2. Ошибка
отличается коротким `{status:HOLD, first_missing:...}` вместо assessment.
Абсолютные пути без reparse обязательны; duplicate JSON keys запрещены.
Файлы перечитываются перед stdout, пары SHA проверяются повторно.
Импорт не меняет stdout, источники, глобальные registries или Decimal context.
UTF-8 настраивается только собственным CLI.

Чистый `engineering_layout_geometry` экспортирует `box`, `intersects`,
`contains`, `attached`, `check_placements`, `free_segments`, `free_rectangles`,
`area_reserve`, `connection_graph`, `search_joint`. Геометрия не имеет доступа
к Case, источникам, ценам или approval. `box` использует XYZ (ширина, высота,
глубина); размер корпуса/аппарата/будущего объекта — HWD. Оси не переставляются,
новых поворотов нет. Числа сериализуются десятичными строками, точность ввода
до 6 знаков, положительный размер до 100000 мм. Вычисляемые размеры полок
округляются вверх до 6 знаков только там, где деление на 3 бесконечно.

## Источники и граница гипотез

Baseline получается через публичный `recommend_composition`, отдельно от
цикла сценариев, с повторным source snapshot после расчёта. Аппаратура идёт
через Device Envelope v0.2 и существующий публичный `planning.prepare`;
нельзя заменять размеры/clearance гипотезами. Консервативный keepout PANEL
учитывает MAX сборки с clearance и корпуса аппарата с manufacturer edge.
151.2 мм тела, 253 мм сборки и 122.5 мм edge сохраняются раздельно.
Неизвестный assembly anchor не выдаётся за размещение сборки: показывается
conservative keepout и `assembly_origin_mm=null`.
Если отдельный body reference отсутствует, assembly origin определяется из
keepout origin прибавлением исходных left/top clearance по осям X/Y; начало
keepout не подменяет начало сборки при ненулевых clearance.

Существующий source-fact adapter сохраняет explicit HWD validate-only и prior
approval/change boundary. KRN36 применяет только прочитанную admitted привязку
3×216 мм, независимо от гипотезы. Неизвестные IP, монтажные плоскости,
анкеры, специальные формы, совместимость и реальная внутренняя геометрия
остаются реальными пробелами. Внешний размер задаёт лишь границу гипотезы
после явных insets; он не становится доказанным внутренним размером.

Каждый кандидат отдельно раскрывает `catalogue_identity`: точные исходные
code/label/family/qualifier, размеры, строку/источник/source issues и имеющиеся
technical/capacity bindings. Полный исходный record остаётся в `strict_baseline`.
`construction_compatibility.status=UNKNOWN` показан отдельно от geometry status,
в том числе в Markdown: прямоугольный `CONDITIONAL_WITNESS` не подтверждает
конструктивную совместимость ВРУ, ШРС, ЩО-70, КРН, КРВ или иной записи.
Исходные причины и пробелы сохраняются без нормализации названий, выдуманных
рейк/модулей/IP/монтажных норм и без изменения прежнего каталога.

Общий API не ограничен именами текущих трёх щитов: аппаратура проходит через
общие source-bound `planning.prepare`/Device Envelope интерфейсы, а dimensions
и history — через прежний source-fact contract. Для иного Case узкая кабельная
проекция возвращает UNKNOWN без заимствования кабелей ЩО6; source admission
аппаратуры и фактов при этом обязателен. Синтетические тесты иных композиций
проверяют только механику модели, не допускают реальные engineering facts.

Узкая проекция кабелей допускает только pinned WU15 PDF и frozen draft/apphash
через существующий code-controlled source adapter. Перечитывается PDF; для
страницы 1 проверяются QF0–20 и точные reviewed tuples тока, фазы, марки,
сечения, длины, группы. ЩО6: 20 отходящих, 60 логических L/N/PE endpoints,
10×3×2.5 — 415 м, 5×3×4 — 293 м, 5×3×6 — 365 м; всего 1073 м.
Необычные QF8/QF9 обе L3 и QF3→Р4/QF5→Р13/QF13→Р3 сохраняются.
QF17 — 3×2.5, 40 м. QF0: марка, жилы и сечение неизвестны. Префикс перед
ВВГ — потеря напряжения, не количество; ПВХ 20/25 не означает cable OD.
Endpoints не создают gland/terminal BOM. Load N остаётся индивидуальным через
каждый 2P RCBO, PE — отдельной ролью. Для НЩР/АВР кабельная проекция этой
версией не допущена: `PROJECT_CABLE_MAPPING_NOT_ADMITTED`, `UNKNOWN`.
Исследовательские расхождения ведомостей других страниц не исправляются.

Фотографии — только qualitative reference. Ни размеры с перспективы, ни
габариты фотографированного АВР, ни свободное место счётчика не используются
как геометрия данного Case или обязательные объекты BOM.

## Запрос сценариев

`engineering_layout.scenarios.v0.1` содержит список `profiles` (1–16).
Каждый профиль имеет ровно `id`, `author`, `version`, `rationale`, `unit=mm`,
`parameters`. Весь профиль имеет origin `SCENARIO`, полный normalized digest,
author/version/rationale и `human_approval=false`; каждый параметр наследует
эту provenance. Параметры никогда не создают CONFIRMED facts. `approved=true`,
готовые placements/cabinet, произвольные источники и неизвестные ключи
отвергаются. Отсутствующее значение не заменяется нулём.

Обязательные параметры:

| Имя | Значение / гипотеза |
|---|---|
| `insets_mm` | top/bottom/left/right/front/back, шесть явных неотрицательных чисел |
| `mount_offset_mm` | явное неотрицательное смещение по глубине |
| `duct_width_mm`, `duct_depth_mm` | ширина corridor и глубина прямоугольного reservation, >0 |
| `connection_height_mm`, `connection_depth_mm` | отдельная полоса подключения каждого аппарата, >0 |
| `service_height_mm` | нижняя полоса entry/N/PE/distribution, >0 |
| `auxiliary_width_mm` | ширина каждой из трёх гипотетических service reservations, >0 |
| `access_width_mm`, `assigned_width_mm` | явные правые полосы, ≥0; ноль допустим только как гипотеза |
| `future_din_hwd_mm`, `future_panel_hwd_mm` | полный keepout будущего объекта либо явный null = неизвестно |

Будущий keepout сам должен включать требуемые clearance/access по гипотезе.
Модель добавляет к нему текущую connection strategy. Это исследовательская
проверка конкретного reference, не универсальная инженерная норма расширения.

Необязательный `routing` содержит ровно `medium=WHOLE_CABLE|INSULATED_CORES`,
`diameter_mm`, `count`, `fill_fraction` (0<f≤1), `usable_width_mm`,
`usable_depth_mm`, `bend_radius_mm`, `termination_max_section_mm2`.
Численные поля положительны, count — целое 1–4096, внутреннее сечение канала
не больше reservation. Явно гипотезируется один диаметр выбранной среды для
всех элементов и один общий trunk. Требуемое число source endpoints/cables и
максимальное подтверждённое сечение нельзя уменьшить этим профилем.
Сравнение πd²count/4 с usable area×fill даёт только условную оценку площади
канала. Для π используется явная верхняя граница 3.141592653589794.
Нет routing — capacity UNKNOWN; feeder остаётся неизвестным даже с routing.
Bend radius как число не доказывает поворот пути: реальные порты, апертуры,
termination compatibility и bend feasibility всё равно UNKNOWN/HOLD.

## Ограниченное семейство поиска

Инфраструктура вычитается ДО packing: левый вертикальный trunk, нижний
service duct/entry/N/PE/distribution, правые access/assigned полосы. Два
порядка зон — PANEL рядом с DIN либо над DIN; перебирается число DIN рядов.
Широкие apparatus keepouts первыми распределяются на наименее занятую полку
с детерминированными id ties. Ряды не требуют 25% резерва каждый: правило
относится к суммарной DIN capacity. Межрядный pitch ровно 140 мм согласно
исходному правилу. Поиск сначала сохраняет legacy `BELOW_ROW_DUCTS`: если
keepout+connection+duct при нескольких рядах требует большего шага, эта
топология даёт `SOURCE_DIN_PITCH_140_INFRASTRUCTURE_CONFLICT`. Затем проверяется
`DIN_COLUMN_RISERS`: после каждой колонки выделен вертикальный канал той же
сценарной ширины/глубины до общего service duct. Ширина колонки — максимум
source keepout width в этой позиции сбалансированных рядов; аппараты прижаты
к её правому каналу, connection расположен сразу под собственным keepout.
Здесь межрядное требование — keepout+connection, без нижнего DIN duct.
Шаг ни одна топология не увеличивает. Для одного ряда проверяется полная высота;
расстояния до следующей рейки в такой модели нет. При KRN36 число и длина
рядов ограничены источником. Во всех остальных случаях это сценарные полки,
не реальные рейки/монтажные анкеры.

Каждый аппарат получает source keepout, отдельный connection reservation и
прямой контакт положительной гранью с производным DUCT, горизонтальным либо
вертикальным. Connection не считается каналом для соседнего аппарата.
На каждом варианте проверяются
containment, depth, пересечения, полные source keepouts, связность duct и
контакт connection/entry/N/PE/distribution. Sharing разрешён только для
пересечения двух каналов в явном сценарном junction, с перечнем пар;
source keepout нельзя waive произвольным overlap relation. Касание не есть
positive-volume collision. Для reservation graph нужна общая грань/объём:
угол/ребро не доказывают связность. Face adjacency не доказывает проход
конкретного cable/cores: route/aperture/bend/port proof отдельно UNKNOWN.

Граф содержит проверенные геометрические edges, достижимость и пути
source endpoints через аппаратные connection reservations к entry либо PE.
Первое присоединение к неизвестному физическому порту — явно гипотетическое;
эти пути не являются электрической схемой. Индивидуальные load N не
соединяются с общей N reservation.

Budget по умолчанию 512 попыток, максимум API 4096; ограничены 256 аппаратов
и 1024 геометрических объекта. Критические координаты выводятся из размеров,
mm grid отсутствует. Найденный witness — `CONDITIONAL_WITNESS`, не победитель,
не global optimum и не physical FIT. `NO_LAYOUT_IN_EXAMINED_FAMILY` означает
только отсутствие решения в данном семействе, не универсальный NO_FIT.
`SEARCH_BUDGET_EXHAUSTED` и unsupported layouts раскрываются явно.
Witness содержит `routing_topology`; `search.routing_topologies` и
`topology_diagnostics` показывают рассмотренные семейства, число попыток и
их ограничения, включая legacy pitch conflict. Budget охватывает все три семейства;
его исчерпание до альтернативы не означает завершённого поиска.
Несколько PANEL без assembly/pair anchors этой версией не моделируются.

Третья family `DIN_SHARED_COLUMN_RISERS` рассматривается после
`BELOW_ROW_DUCTS` и `DIN_COLUMN_RISERS`. Один вертикальный канал полной
сценарной ширины обслуживает пару соседних колонок: левые footprint выровнены
правой гранью к каналу, правые — левой. Это сохраняет прямое примыкание
каждой отдельной CONNECTION при разных source widths. У нечётной последней
колонки остаётся свой канал; пустая ячейка не создаёт аппарат или нагрузку.
Коллизии и source keepouts проверяются без нового sharing-разрешения.
Общий канал списывается ровно один раз через union проекций; обе стороны
не удваивают его расход и не превращают канал в свободный резерв.
DUCT-only сеть должна быть связна; CONNECTION не проводит транзит между
каналами, а source endpoint paths проходят только через DUCT до entry/PE.

Для shared witness добавляется `SHARED_DUCT_BRANCH_COMPATIBILITY_UNKNOWN`:
двусторонний геометрический контакт не доказывает physical wire fill,
thermal/bend/port/termination compatibility. Необязательный common-trunk
capacity расчёт этого пробела не закрывает. Без соответствующих источников
physical HOLD сохраняется; размеры, clearances, шаг 140 мм и независимый
резерв ≥25% не меняются. Старые две family и порядок их witnesses сохранены.

## Резерв и повторная проверка

DIN/PANEL независимы и требуют ≥25% общего свободного ресурса каждой зоны.
DIN возвращает фактические free segments и capacity/occupied/blocked/free.
Внутренние risers занимают rail capacity: их проекции входят в объединение
недоступных интервалов на каждом пересекаемом ряду. Подтверждённые KRN36
3×216/648 мм остаются полным знаменателем, не сокращаются ради резерва.
PANEL использует точное объединение проекций reservations, затем disjoint
free rectangles; перекрывающиеся объекты не списываются дважды. Глубина и
containment проверяются отдельно, проекция для резерва консервативна.
Joint operational proof отдельно размещает future body и connection,
проверяет обе геометрии на containment/коллизии и прямой контакт connection
с DUCT. Критические позиции выводятся из граней reservations; DIN reference
остаётся на существующем row origin с его height budget.
DIN добавляет `future_witness={body,connection}`. PANEL сохраняет прежний
`future_witness` Box полного envelope и добавляет `future_body_witness` и
`future_connection_witness`; недоказанное размещение даёт `NO_REFERENCE_FIT`,
отсутствующий reference — `UNKNOWN`. Чистая функция `area_reserve` сохраняет общий
контракт прямоугольного reference; только joint proof добавляет подключение.
Инфраструктура вне монтажных зон исключается из их capacity с явной границей,
а не называется свободной. Geometric free не равно operational spare.
Reference должен помещаться с connection geometry и не пересекать duct.
Фрагментированные scraps, не вмещающие reference, не считаются доказанным
operational reserve. Null reference даёт UNKNOWN даже при scalar ≥25%.
Старые strict planning proofs сохраняются отдельно без пересчёта их смысла.

Sensitivity сравнивает первый именованный профиль со всеми остальными:
явные parameter differences, все 70 candidate statuses и изменения геометрии/
ограничений по щитам. В отчёте нет встроенных численных presets. Проверочные
runtime-профили создаются отдельно до оценки с автором Codex и rationale;
они одинаковы для всех кандидатов и не становятся WU engineering evidence.

Targeted tests и relevant regressions выполняются до финального five-file
freeze, затем parent запускает final-delta full suite, после него fresh
independent review. Требуются scoped Black/Ruff/Mypy и configured Mypy.
Существующие 117 Ruff / 2 Black старого `.autopilot` остаются отдельным
canonical FAIL. Stage/commit/push, новые зависимости, источники, Excel,
реальные approval/Case apply/production/downstream здесь не разрешены.

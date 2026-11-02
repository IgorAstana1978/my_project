# Продолжение WU: прямой допуск стандартных METAL строк 8–47

2026-10-30, после исходного CAD-аудита ниже, Игорь дал новое прямое Human Decision изготовителя:

> Все стандартные METAL строк 8–47 каталога имеют наружную дверь и монтажную панель, без фальшпанели. Внутренняя дверь — отдельное исполнение.

**Текущий результат: 40 exact identities допущены для H−100/W−80 через явный opt-in; остальные 9 METAL и 21 KRN/KRV остаются HOLD.** Утверждение «49 HOLD / 0 допусков» в исходном отчёте ниже описывает предыдущий этап, до нового решения, и сохраняется как историческое evidence. Новых CAD/сборочных подтверждений не создавалось.

Authority: `IGOR-DINVA-METAL-STANDARD-CONSTRUCTION-ROWS8-47-20261030`, `IGOR_DIRECT_HUMAN_DECISION`, дата `2026-10-30`. Версия каталога строго `2026.10.21`, SHA256 `be4a3497cf86ee4e5a13ac55bfeeeb980e6948cd30847ae027f36d6ca599cc71`.

## Exact source provenance и применение

Дословное текущее user message, chat/session locator, timestamp, SHA исходной строки и SHA UTF-8 текста сохранены отдельно от технической проекции 40 identities:

`C:/Users/IgorN/.codex/visualizations/2026/10/30/01a18cd5-327b-7d63-befa-6cf988eed444/standard-metal-manufacturer-decision-20261030-v01/igor-direct-manufacturer-decision.json`

SHA256 authority artifact: `d2339f9fb76b394a11d399273f7eb8b8374c197913870a3d857a463c295897be`.
SHA256 дословного user message: `284f7f8260f6d3a7900a81fd4c8d295f0a1f80f8cc5cf4dec4b706f6001b2f48`.

В том же versioned evidence-каталоге находятся 40 `metal-row-{row}.json`, созданных без overwrite. Каждый сохраняет existing exact four-field contract: schema, одна exact catalogue identity, стандартное execution и два raw source path/SHA (authority artifact и оригинальный каталог). Техническая проекция identities не выдаётся за самостоятельное Human Decision. SHA каждого binding зафиксирован в `cabinet_sizing_evidence.METAL_STANDARD_BINDINGS` и admitted только existing ролью `metal_standard_construction` в `AUTHORIZED`; raw JSON approval flags и caller SHA допуска не создают.

```python
binding = standard_construction_binding("CATALOGUE-METAL-ROW-37")
report = assess_panel("CATALOGUE-METAL-ROW-37", construction_binding=binding)
verify_assessment(report)
```

Helper возвращает копию binding только для exact code и версии `2026.10.21`; неизвестные identities, другие версии и `CURRENT` дают `SizingHold`, без fallback. `assess_panel(..., construction_binding=None)` сохраняет прежний HOLD. Допуск не выбирает корпус и не меняет production defaults. Указание внутренней двери/другого исполнения не покрывается стандартным binding.

Отсутствующие локальные source artifacts, drift authority/каталога/binding, изменения identity/execution и подмена отчёта блокируют применение. Reader, schema, absolute/reparse/duplicate/SHA checks и повторное чтение сохранены.

## 40 допущенных identities: проверка формулы, без выбора корпуса

| Exact catalogue code | Наружные В×Ш×Г, мм | Панель В×Ш, мм |
|---|---|---|
| `CATALOGUE-METAL-ROW-8` | 300×300×150 | 200×220 |
| `CATALOGUE-METAL-ROW-9` | 300×300×200 | 200×220 |
| `CATALOGUE-METAL-ROW-10` | 300×400×150 | 200×320 |
| `CATALOGUE-METAL-ROW-11` | 300×400×200 | 200×320 |
| `CATALOGUE-METAL-ROW-12` | 400×300×150 | 300×220 |
| `CATALOGUE-METAL-ROW-13` | 400×300×200 | 300×220 |
| `CATALOGUE-METAL-ROW-14` | 400×300×250 | 300×220 |
| `CATALOGUE-METAL-ROW-15` | 400×600×200 | 300×520 |
| `CATALOGUE-METAL-ROW-16` | 400×600×250 | 300×520 |
| `CATALOGUE-METAL-ROW-17` | 400×600×300 | 300×520 |
| `CATALOGUE-METAL-ROW-18` | 500×300×150 | 400×220 |
| `CATALOGUE-METAL-ROW-19` | 500×300×200 | 400×220 |
| `CATALOGUE-METAL-ROW-20` | 500×400×150 | 400×320 |
| `CATALOGUE-METAL-ROW-21` | 500×400×200 | 400×320 |
| `CATALOGUE-METAL-ROW-22` | 500×400×250 | 400×320 |
| `CATALOGUE-METAL-ROW-23` | 500×500×200 | 400×420 |
| `CATALOGUE-METAL-ROW-24` | 500×500×250 | 400×420 |
| `CATALOGUE-METAL-ROW-25` | 600×400×150 | 500×320 |
| `CATALOGUE-METAL-ROW-26` | 600×500×150 | 500×420 |
| `CATALOGUE-METAL-ROW-27` | 600×400×200 | 500×320 |
| `CATALOGUE-METAL-ROW-28` | 600×400×250 | 500×320 |
| `CATALOGUE-METAL-ROW-29` | 600×500×200 | 500×420 |
| `CATALOGUE-METAL-ROW-30` | 600×500×250 | 500×420 |
| `CATALOGUE-METAL-ROW-31` | 600×600×200 | 500×520 |
| `CATALOGUE-METAL-ROW-32` | 600×600×250 | 500×520 |
| `CATALOGUE-METAL-ROW-33` | 600×600×300 | 500×520 |
| `CATALOGUE-METAL-ROW-34` | 700×500×200 | 600×420 |
| `CATALOGUE-METAL-ROW-35` | 700×500×250 | 600×420 |
| `CATALOGUE-METAL-ROW-36` | 800×600×200 | 700×520 |
| `CATALOGUE-METAL-ROW-37` | 800×600×250 | 700×520 |
| `CATALOGUE-METAL-ROW-38` | 800×600×300 | 700×520 |
| `CATALOGUE-METAL-ROW-39` | 800×800×200 | 700×720 |
| `CATALOGUE-METAL-ROW-40` | 800×800×250 | 700×720 |
| `CATALOGUE-METAL-ROW-41` | 800×800×300 | 700×720 |
| `CATALOGUE-METAL-ROW-42` | 1000×600×250 | 900×520 |
| `CATALOGUE-METAL-ROW-43` | 1000×600×300 | 900×520 |
| `CATALOGUE-METAL-ROW-44` | 1000×800×250 | 900×720 |
| `CATALOGUE-METAL-ROW-45` | 1000×800×300 | 900×720 |
| `CATALOGUE-METAL-ROW-46` | 1200×800×300 | 1100×720 |
| `CATALOGUE-METAL-ROW-47` | 1200×1000×300 | 1100×920 |

Строки METAL 48–56 (включая M51 без qualifier), KRN/KRV, внутренние двери и иные исполнения этим решением не допускаются. Никакой вывод исполнения из DXF filenames, qualifier или наружных HWD не используется.

Usable geometry/depth остаются UNKNOWN, physical FIT — HOLD, stop-before HUMAN_APPROVAL_1. Без фальшпанели не означает подтверждённую полезную глубину или пригодность конкретных аппаратов. Цены, Case, каталог, historical replay и production не менялись; commit/push не выполнялись.

## Воспроизводимость и сохранность предыдущего WU

Локальный read-only `replay_admission.py` рядом с authority artifact использует свежий каталог и существующие публичные API: для 40 identities — assessment плюс verify_assessment; для остальных 30 — HOLD. Выходной `real-admission-replay.json` не является source admission или Human Approval. Portable pytest fixtures проверяют механику на синтетической полной raw source chain; реальные 40 HWD проверяются локальным replay.

Существующие 60 tests предыдущего WU сохранены; новые cases проверяют exact roster, explicit opt-in, все 40 codes, границу версий/identities, raw source drift и недопустимые исполнения. Предыдущие `standard-metal-audit.complete.json`, `standard-metal-closeout.json` и их SHA сохранены без overwrite. Копии двух reviewed файлов до нового решения находятся в новом evidence-каталоге под именами `before-...`; прежний audit doc SHA `d706d819973b54bf13819052858511a0f9de02b1243e6e3d223a5e8af1c29891`, tests SHA `4c1e4f49e732b56c23f589bf350eb53a82a36a67b03b0608d35dd29b59f74d14`.

---

## Исходный CAD-аудит до нового прямого решения (сохранён дословно)

# Source-bound Standard METAL Construction Admission v0.1 — аудит

Дата: 2026-10-30. Исходный baseline: `main@c206d9ec6f653ee388a26d42004c491a52781a6e`, рабочее дерево и staging были пусты.

**Результат: 0 допусков, 49/49 METAL — HOLD.** Отдельного сборочного источника нет; Игорь прямо подтвердил: «Дополнительного источника нет — оставить HOLD».

Это исследовательский отчёт, не construction binding, Human Approval или источник роли `metal_standard_construction`. Runtime, `AUTHORIZED` и действующий source-admission contract не изменены. Непустой qualifier не разрешает стандартное исполнение, пустой qualifier тоже не доказывает его.

## Проверенные источники

- Каталог: `C:/Users/IgorN/Documents/invoice_quote_filler_data/prices/current/прайс_металл_лотки_крышки с 2026.10.21.xlsx`.
- Версия `2026.10.21`, SHA256 `be4a3497cf86ee4e5a13ac55bfeeeb980e6948cd30847ae027f36d6ca599cc71`. Чтение через действующий `cabinet_catalogue.inventory`: 70 записей, 49 METAL / 13 KRN / 8 KRV.
- `C:/Users/IgorN/Downloads/1.rar`: SHA256 `ba881c13c744a3fea1cb4439e253d797ed0770ef74be1a3ee40d9339c0bacb1d`, 38 файлов, 20 основных DXF.
- `C:/Users/IgorN/Downloads/КРН.rar`: SHA256 `924660f0b24e8cd3ad2cfe0fada15ca6e4f947f2a653225ab049034105ee3365`, 42 файла, 21 основной DXF и 6 backup/original.
- 41 основной DXF entry / 40 уникальных SHA. Повторный `krn-kyrn nnn.dxf` — один источник, не независимое подтверждение. Чтение архивов в память, без распаковки на диск.
- Правило Игоря `IGOR-DINVA-METAL-MOUNTING-PANEL-20261030` из `docs/dinva_metal_mounting_panel_v0_1.md`: H−100/W−80 только для отдельно доказанного стандартного исполнения с наружной дверью и монтажной панелью.

Ни один исследованный комплект не устанавливает проверяемую цепочку exact catalogue identity → актуальная сборочная revision → стандартное исполнение → наружная дверь и монтажная панель. Геометрическая похожесть деталей, плоские контуры, имя файла, наружные размеры и отсутствие qualifier этой цепочкой не являются.

## Проверка всех 49 identities

Все строки относятся к семейству `METAL`, источнику выше, листу `Лист1`. Наименование читается из `A{row}`, наружные В×Ш×Г из `E{row}/F{row}/G{row}`. В таблице сохранён точный label как JSON string, включая пробел перед закрывающей кавычкой.

`E1` = `HOLD_STANDARD_CONSTRUCTION_EVIDENCE_REQUIRED` (41 запись); `E2` = `HOLD_PANEL_SPECIAL_OR_UNCONFIRMED_CONSTRUCTION` (8 записей). Везде `panel_hw_mm=null`, `construction_binding=null`. CAD-ссылки в последней колонке — только поиск по имени, **не доказанное соответствие**; отсутствие такой ссылки не исключает деталей в смешанных чертежах.

| Catalogue identity | Точный label | Наружные В×Ш×Г, мм | Итог | Навигационные имена DXF в `1.rar` |
|---|---|---|---|---|
| `CATALOGUE-METAL-ROW-8` | `"300х300х150 "` | 300×300×150 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-9` | `"300х300х200 "` | 300×300×200 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-10` | `"300х400х150 "` | 300×400×150 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-11` | `"300х400х200 "` | 300×400×200 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-12` | `"400х300х150 "` | 400×300×150 | HOLD / E1 | `1/ШКАФЫ/400х300х150.dxf` |
| `CATALOGUE-METAL-ROW-13` | `"400х300х200 "` | 400×300×200 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-14` | `"400х300х250 "` | 400×300×250 | HOLD / E1 | `1/ШКАФЫ/ящик 400х300х250 внутреняя дверь.dxf`<br>`1/ШКАФЫ/ящик 400х300х250 — копия.dxf` |
| `CATALOGUE-METAL-ROW-15` | `"400х600х200 "` | 400×600×200 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-16` | `"400х600х250 "` | 400×600×250 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-17` | `"400х600х300 "` | 400×600×300 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-18` | `"500х300х150 "` | 500×300×150 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-19` | `"500х300х200 "` | 500×300×200 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-20` | `"500х400х150 "` | 500×400×150 | HOLD / E1 | `1/ШКАФЫ/ящик 500х400х150.dxf` |
| `CATALOGUE-METAL-ROW-21` | `"500х400х200 "` | 500×400×200 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-22` | `"500х400х250 "` | 500×400×250 | HOLD / E1 | `1/ШКАФЫ/500х400х250 внутр.dxf` |
| `CATALOGUE-METAL-ROW-23` | `"500х500х200 "` | 500×500×200 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-24` | `"500х500х250 "` | 500×500×250 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-25` | `"600х400х150 "` | 600×400×150 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-26` | `"600х500х150 "` | 600×500×150 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-27` | `"600х400х200 "` | 600×400×200 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-28` | `"600х400х250 "` | 600×400×250 | HOLD / E1 | `1/ШКАФЫ/600х400х250 внутр.dxf` |
| `CATALOGUE-METAL-ROW-29` | `"600х500х200 "` | 600×500×200 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-30` | `"600х500х250 "` | 600×500×250 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-31` | `"600х600х200 "` | 600×600×200 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-32` | `"600х600х250 "` | 600×600×250 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-33` | `"600х600х300 "` | 600×600×300 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-34` | `"700х500х200 "` | 700×500×200 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-35` | `"700х500х250 "` | 700×500×250 | HOLD / E1 | `1/ШКАФЫ/700х500х250,,,ип54.dxf`<br>`1/ШКАФЫ/ящик 700х500х250 внут дверь.dxf` |
| `CATALOGUE-METAL-ROW-36` | `"800х600х200 "` | 800×600×200 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-37` | `"800х600х250 "` | 800×600×250 | HOLD / E1 | `1/ШКАФЫ/800х600х250 внутр.dxf`<br>`1/ШКАФЫ/ящик 800х600х250.dxf` |
| `CATALOGUE-METAL-ROW-38` | `"800х600х300 "` | 800×600×300 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-39` | `"800х800х200 "` | 800×800×200 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-40` | `"800х800х250 "` | 800×800×250 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-41` | `"800х800х300 "` | 800×800×300 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-42` | `"1000х600х250 "` | 1000×600×250 | HOLD / E1 | `1/ШКАФЫ/ящик 1000х600х250.dxf` |
| `CATALOGUE-METAL-ROW-43` | `"1000х600х300 "` | 1000×600×300 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-44` | `"1000х800х250 "` | 1000×800×250 | HOLD / E1 | `1/ШКАФЫ/ящик 1000х800х250.dxf` |
| `CATALOGUE-METAL-ROW-45` | `"1000х800х300 "` | 1000×800×300 | HOLD / E1 | — |
| `CATALOGUE-METAL-ROW-46` | `"1200х800х300 "` | 1200×800×300 | HOLD / E1 | `1/ШКАФЫ/1200х800х300.dxf` |
| `CATALOGUE-METAL-ROW-47` | `"1200х1000х300 "` | 1200×1000×300 | HOLD / E1 | `1/ШКАФЫ/ящик 1200х1000х300.dxf` |
| `CATALOGUE-METAL-ROW-48` | `"1300х800х350 напольн. "` | 1300×800×350 | HOLD / E2 | — |
| `CATALOGUE-METAL-ROW-49` | `"1500х500х350 ШРС "` | 1500×500×350 | HOLD / E2 | `1/шрс 1500х500х350.dxf` |
| `CATALOGUE-METAL-ROW-50` | `"1600х700х350 ШРС "` | 1600×700×350 | HOLD / E2 | `1/шрс 1600х700х350.dxf` |
| `CATALOGUE-METAL-ROW-51` | `"1700х1000х500"` | 1700×1000×500 | HOLD / E1 | `1/7Бека7вру 1700,1000,500.dxf` |
| `CATALOGUE-METAL-ROW-52` | `"1700х800х500 ВРУ "` | 1700×800×500 | HOLD / E2 | `1/7Бека7вру 1700,800,500.dxf` |
| `CATALOGUE-METAL-ROW-53` | `"2000х800х500 ПР "` | 2000×800×500 | HOLD / E2 | — |
| `CATALOGUE-METAL-ROW-54` | `"2000х1000х500 ПР "` | 2000×1000×500 | HOLD / E2 | — |
| `CATALOGUE-METAL-ROW-55` | `"2000х800х600 ЩО70 "` | 2000×800×600 | HOLD / E2 | — |
| `CATALOGUE-METAL-ROW-56` | `"2000х1000х600 ЩО70 "` | 2000×1000×600 | HOLD / E2 | — |

В папке `ШКАФЫ` 14 DXF: 12 без текстовых подписей; у `1200х800х300.dxf` только размерная аннотация R10, у `800х600х250 внутр.dxf` — `1mm`. Это не assembly BOM, не execution declaration и не exact mapping. Пары вариантов для M14/M35/M37 не сведены автоматически к одной revision.

В смешанных DXF встречается `ip54...500*400*250`, но это unitless/многомодельная аннотация, а не допуск M22. Три уникальных mixed DXF имеют `$INSUNITS=0`. Единственная явная подпись `naruzhnaya dver` найдена в `КРН/krn18 vnytryanka.dxf`, SHA256 `1b7b1dc35f3c3575fcd291a8e8bea242e1c60f20b8f687213c655c2ee5a03d89`; она относится к другому семейству и не подтверждает METAL.

У M51 label без qualifier, но имя DXF содержит `вру`; ни отсутствие qualifier, ни такое имя не разрешают стандартное исполнение. Чертёж `шрс 1700х700х400.dxf` не имеет точной HWD-позиции в текущем каталоге; перенос на соседние размеры запрещён.

## Проверки и воспроизведение

Локальный исследовательский репродуктор (вне runtime):

`C:/Users/IgorN/.codex/visualizations/2026/10/30/01a18cd5-327b-7d63-befa-6cf988eed444/audit_standard_metal.py`.

Запуск из корня репозитория существующим `.venv/Scripts/python.exe -B` печатает JSON в stdout. Он повторно проверяет архивы, сохраняет entry/SHA/bytes и DXF text chunks, читает каждую из 49 позиций через `assess_panel` и вызывает `verify_assessment`. Filename matches выделены отдельно и не используются для допуска. Исходные файлы не меняются.

Полные exact catalogue identities, source path/SHA/cells и raw DXF entry/SHA сохраняются во внешнем `standard-metal-audit.complete.json` рядом с репродуктором. Ни репродуктор, ни его JSON не внесены в `AUTHORIZED`.

В `tests/test_dinva_metal_mounting_panel.py` сохранены исходные проверки raw/construction SHA drift, повторного чтения каталога/источника, identity mismatch и подмены отчёта. Добавлены атаки: перенос binding при равных HWD на другую row/label/source identity; подмена report identity; `status=PASS`; превращение HOLD в заявленный расчёт панели без admission. Все источники в tests синтетические и не допускают реальные корпуса.

## Сохранённые границы и первый blocker

Подбор и ранжирование корпусов не выполнялись. Каталог, наружные размеры, цены, Case, historical replay, production и approval gates сохранены. Usable geometry/depth остаются UNKNOWN, physical FIT — HOLD. Размеры панели не передаются в packing и не создают Human Approval.

Первый blocker: отсутствует source-backed связь конкретного каталожного исполнения с наружной дверью и монтажной панелью. Для дальнейшего допуска нужен отдельный сборочный источник изготовителя с точной catalogue identity, составом, исполнением и действующей CAD revision. До его получения real bindings не создаются; новый источник потребует отдельной проверки, а не переноса текущего HOLD в PASS.

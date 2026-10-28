# Предварительные рекомендации по корпусам v0.1

Модуль `scripts/cabinet_preliminary_recommendations.py` предоставляет отдельный
read-only слой над публичным strict selector v4. Его схема
`cabinet_sizing.preliminary_recommendations.v0.1` не является техническим
подтверждением, выбором корпуса или артефактом HUMAN_APPROVAL_1.
Действующий strict verifier отклоняет эту схему в обоих режимах проверки.
Strict API, default v4, historical replay и physical HOLD сохраняются.

## Запуск

Из корня проекта, указывая абсолютный путь входа:

```powershell
& .venv/Scripts/python.exe -B scripts/cabinet_preliminary_recommendations.py `
  --case-id CASE-ID --composition-json C:/absolute/path/composition.json
```

Для читаемого русского представления добавьте `--format markdown`.
По умолчанию stdout содержит JSON. Можно передать конкретный текущий strict
request парой `--request-json C:/absolute/path/request.json --request-sha256 SHA256`.
Request обязан иметь schema `cabinet_sizing.catalogue_request.v0.4`;
исторические запросы воспроизводятся прежними API, а не этим слоем.
Только `source_facts` сужается для каждого item; общий `devices` сохраняется целиком.
При отсутствии request используется существующий публичный default request.

CLI ничего не записывает и не имеет output, apply, approval или report-input
параметров. Отчёт печатается только после recompute и повторного чтения входных
файлов. Exit code **2** сохраняется, если хотя бы один strict item находится на
HOLD; при валидных полных доказательствах это совместимо с полезным advisory
JSON/Markdown. Exit code **0** означает отсутствие strict item HOLD, но не Human
Approval. Ошибка источника/схемы/SHA/coverage/drift даёт только JSON HOLD без advice.
Неверные аргументы отклоняет argparse. JSON duplicate keys запрещены; входные пути
должны быть абсолютными, без symlink/reparse. Кодировка нового CLI — UTF-8;
импорт модуля не меняет stdout, locale или глобальные настройки strict-кода.

## Публичный Python API

```python
report = recommend_composition(case_id, items, request=None)
verify_recommendations(report, items, expected_case_id=case_id)
text = format_recommendations(report, items, expected_case_id=case_id)
```

API импортируются из `cabinet_preliminary_recommendations` при обычном project
`scripts` в Python path. `verify_recommendations` возвращает `None` при точном
совпадении с полным повторным расчётом и бросает `cabinet_sizing.SizingHold` при
ошибке. Formatter тоже вызывает verifier: импортированный JSON не становится
источником доверенных strict-диагностик. Входные items/request не меняются.

## Как читать результат

Для каждого щита все **70 кандидатов** представлены один раз в `candidates`:
49 METAL, 13 KRN и 8 KRV. Остальные списки ссылаются на их ID. Сохраняются
исходные strict status, первый HOLD, reasons, физический статус, source HWD,
layout, DIN/PANEL reserve и частичная DIN assessment, если она есть.
`counts` всегда содержит FIT, NO_FIT и UNKNOWN, включая нулевые значения.

- `supported_frontier`: компонентный Pareto по внешним В×Ш×Г среди strict FIT.
  Кандидат доминируется, только если другой не больше по каждой оси и меньше
  хотя бы по одной. Разные ID одинаковых размеров сохраняются.
- `layout_alternatives`: такие же фронты внутри описательных сигнатур уже
  существующего strict proof: orientation, zone arrangement/kinds и DIN row count.
  Это дополнительные варианты существующей планировки, без предпочтения схемы.
- `shortlist`: объединение этих фронтов с удалением повторов только по ID.
  `supported_candidates` оставляет доступными и остальные strict FIT: размерное
  доминирование не переводит их в NO_FIT.
- `unknown_candidates`: все UNKNOWN, в том числе те, чьи внешние размеры меньше
  известных FIT. `unresolved_dimensional_frontier` показывает UNKNOWN на общем
  необходимом размерном фронте FIT+UNKNOWN; это не доказательство вместимости.
- `conditional_candidates`: UNKNOWN с подтверждённым частичным DIN capacity PASS,
  даже если их внешние размеры не попали на unresolved frontier. Неподтверждённые
  глубина/монтаж/IP/PANEL остаются видимыми и удерживают общий UNKNOWN/HOLD.
- `excluded_no_fit`: только исходные strict NO_FIT с неизменными reasons/proof.
  Это вывод в границах исходной модели, а не перебор новых физических ориентаций.

Естественный одиночный supported frontier остаётся локальным неполным shortlist.
Отчёт не содержит выбранного корпуса или назначения Case. Нет рейтинга по цене,
семейству, объёму или «комфортному запасу»; минимальное количество вариантов не задано.

## Что доказано и что остаётся неизвестным

Проверенные размеры аппаратов и body/assembly/reference distinctions берутся
из существующего approved Device Envelope v0.2 через strict API. Новая физика,
новые зазоры, перестановки или 90° rotation mapping не добавляются.

Для METAL required HWD и независимый DIN/PANEL reserve — планировочная модель
внешних габаритов. `outer_minus_required_mm` — только арифметическая разность
внешнего HWD и требуемого моделью HWD; `NON_USABLE_PLANNING_HEADROOM` прямо
запрещает трактовать её как внутренний полезный зазор или безопасный запас.
Свободная планировочная площадь PANEL не доказывает свободную монтажную площадь.
Положение body plane, DIN offsets, кабели, клеммы, service geometry, IP,
factory anchors/layout требуют отдельного инженерного evidence, если его нет
в strict proof. KRN36 216 мм на рейку/648 мм суммарно — только существующее
частичное DIN evidence; оно не доказывает монтаж или полезную глубину. Для KRV
цифры в имени и данные другого корпуса не становятся capacity evidence.

## Источники и защита от дрейфа

Источник допускается существующим code-controlled strict admission, а не SHA
или approval-полем произвольного JSON. Отчёт сохраняет конкретный strict request
с версиями/path/SHA, provenance каталога и все исходные per-candidate bindings.
Текущий источник каталога — уже одобренная версия `2026.10.21`; прежние схемы
strict остаются за прежними API. Фактические pins берутся из request/proof,
а не из изменяемого алиаса `CURRENT` в сохранённом отчёте.

Слой сверяет Case/item/apparatus hash, полные 70 уникальных ID, исходные записи,
ряды и семейства с заново прочитанным admitted inventory. `strict_evaluation_sha256`
фиксирует весь strict snapshot. Повторный strict snapshot вокруг построения
advice обнаруживает source/report/input drift. Verifier заново делает весь расчёт
по сохранённому request и текущим items и сравнивает отчёт целиком.
Полный source-backed HOLD допускает advice; HOLD без валидных полных диагностик
не создаёт запасного списка. Markdown содержит основания и gaps всех 70 кандидатов.

Слой не пишет Case/BOM/Excel/цены, не меняет cabinets в items, не выполняет
Human Approval, builder apply, КП или downstream. Новое решение о корпусе и
размерах требует самостоятельного прямого Human Approval по прежнему контракту.

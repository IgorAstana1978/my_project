# Acceptance Criteria: Invoice Quote v0.2.1 Drawing/Media Snapshot Helper

## 1. Назначение Helper

Будущий helper нужен для проверки сохранности drawing/media chain в `.xlsx`.

Helper должен:

- работать на ZIP-level;
- быть отдельным проверочным контуром;
- не быть интеграцией с writer на этом шаге;
- не работать с реальным шаблоном на этом шаге;
- не реализовывать dynamic row insertion.

## 2. Что Должен Snapshot

Будущий snapshot должен фиксировать:

- список `xl/media/*`;
- список `xl/drawings/*`;
- список `xl/drawings/_rels/*`;
- worksheet drawing references;
- hashes relevant drawing/media parts;
- relationships между worksheet/drawing/media parts.

Snapshot должен быть пригоден для детерминированного сравнения before/after.

## 3. Positive Acceptance Criteria

Успешный сценарий считается принятым, если:

- искусственный `.xlsx` package создаётся в `tmp_path`;
- snapshot before и after совпадают;
- helper возвращает детерминированный результат;
- порядок файлов не влияет на сравнение;
- реальные `.xlsx` не используются и не добавляются в Git.

## 4. Negative Acceptance Criteria

Fail-closed сценарии считаются принятыми, если helper возвращает ошибку, когда:

- удалён media file;
- изменён media file hash;
- удалён drawing XML;
- изменён drawing XML hash;
- удалён relationship;
- изменён relationship;
- исчез worksheet drawing reference;
- snapshot невозможно построить.

На уровне будущей интеграции temp/partial output должен очищаться при ошибке.

## 5. Что НЕ Должен Делать Helper

Helper не должен:

- редактировать drawing XML;
- переносить anchors;
- чинить повреждённые drawings;
- менять workbook;
- сохранять workbook;
- использовать openpyxl как основной источник истины для media/drawing package;
- подключаться к isolated writer на этом шаге;
- подключаться к v0.2 separate layer.

## 6. Тестовая Стратегия

Тестовая стратегия для будущего code step:

- тесты должны создавать минимальный искусственный `.xlsx` ZIP-package в
  `tmp_path`;
- реальные `.xlsx` fixtures не хранить в Git;
- сначала тестировать helper отдельно;
- потом отдельным будущим шагом подключать к isolated writer;
- negative tests должны проверять fail-closed ошибки;
- тесты должны проверять, что `.xlsx` и manifest не появляются в Git changes.

## 7. Human Approval Points

Отдельное подтверждение Игоря требуется на:

- переход от acceptance criteria к code step;
- подключение helper к isolated writer;
- использование реального Excel-шаблона;
- добавление `.xlsx` в Git;
- подключение к v0.2 separate layer;
- writer mode;
- dynamic row insertion;
- использование generated output как клиентского КП.

## 8. Definition Of Done

Документ считается готовым, если:

- создан только один markdown-файл acceptance criteria;
- код не менялся;
- tests не менялись;
- `.xlsx` не добавлялись;
- manifest не создавался;
- старый MVP и v0.2 separate layer не трогались;
- `scripts/fill_invoice_quote_extended.py` не трогался;
- `git diff --check` чистый;
- документ согласован до commit.

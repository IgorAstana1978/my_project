# Invoice Quote Filler v0.2.1 Drawing/Media Snapshot Design

## 1. Назначение

Drawing/media chain - рискованная часть `.xlsx`, потому что логотипы,
печати, подписи, изображения, anchors и drawing relationships хранятся не как
обычные значения ячеек, а как связанные XML и binary parts внутри ZIP-пакета.

Текущий isolated extended writer уже проверяет:

- formulas;
- header ranges;
- signature range;
- merged ranges.

Проверка drawing/media chain пока не реализована. Этот документ описывает
будущий безопасный design и не является code step.

## 2. Что Нужно Защищать

Будущая проверка drawing/media chain должна защищать:

- embedded images;
- drawings;
- anchors/positions;
- relationships в `xl/drawings/_rels`;
- media files в `xl/media`;
- worksheet drawing references;
- package structure `.xlsx`;
- отсутствие потери логотипов, подписей, печатей, изображений и графических
  объектов.

## 3. Возможный Подход К Snapshot

Безопасный первый подход должен быть read-only и ZIP-level:

- рассматривать `.xlsx` как ZIP;
- снять список файлов `xl/media/*`;
- снять список файлов `xl/drawings/*`;
- снять список `xl/drawings/_rels/*`;
- снять worksheet drawing references;
- сохранить hashes relevant drawing/media parts;
- сравнивать before/after после генерации output.

Snapshot должен быть детерминированным и не должен пытаться интерпретировать
Excel layout шире, чем нужно для проверки сохранности drawing/media chain.

## 4. Fail-Closed Criteria

Будущая проверка должна останавливаться fail-closed:

- если пропал media file - ошибка;
- если появился неожиданный media/drawing file - ошибка или WARN по отдельному
  решению;
- если изменился hash drawing/media part - ошибка;
- если изменились relationships - ошибка;
- если исчез worksheet drawing reference - ошибка;
- если snapshot невозможно построить - generation должна остановиться
  fail-closed.

## 5. Что НЕ Делать На Первом Шаге

На первом шаге нельзя:

- редактировать drawing XML;
- переносить anchors;
- пытаться чинить повреждённые drawings автоматически;
- делать dynamic row insertion;
- использовать реальный `.xlsx`;
- подключать это к v0.2 separate layer;
- считать output клиентским КП.

## 6. Тестовая Стратегия

Будущие тесты должны оставаться изолированными:

- тестовый `.xlsx` создавать кодом в `tmp_path`;
- если openpyxl не создаёт полноценный drawing/media chain без внешних
  ресурсов, сначала сделать отдельный ZIP-level helper test на искусственном
  `.xlsx` package;
- positive test: drawing/media snapshot совпадает;
- negative test: удалён media file -> fail-closed;
- negative test: изменён relationship -> fail-closed;
- negative test: изменён drawing XML -> fail-closed;
- temp/partial output очищается при ошибке;
- реальные `.xlsx` не добавляются в Git.

## 7. Интеграция С Isolated Extended Writer

Безопасный будущий путь интеграции:

- сначала отдельный helper без интеграции;
- потом тесты helper;
- потом подключение helper к `generate_extended_workbook`;
- затем positive/negative tests в isolated writer;
- только после этого думать о реальном шаблоне.

Подключение к v0.2 separate layer должно оставаться отдельным будущим решением,
а не частью drawing/media snapshot spike.

## 8. Human Approval Points

Отдельное подтверждение Игоря требуется на:

- использование реального Excel-шаблона;
- добавление реального `.xlsx` в Git;
- изменение логики сохранения workbook;
- подключение к v0.2 separate layer;
- writer mode;
- dynamic row insertion;
- использование generated output как клиентского КП.

## 9. Definition Of Done

Документ считается готовым, если:

- создан только один markdown-файл design;
- код не менялся;
- tests не менялись;
- `.xlsx` не добавлялись;
- manifest не создавался;
- старый MVP и v0.2 separate layer не трогались;
- `git diff --check` чистый;
- документ согласован до commit.

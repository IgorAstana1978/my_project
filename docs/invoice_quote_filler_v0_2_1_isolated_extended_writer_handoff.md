# Invoice Quote Filler v0.2.1 Isolated Extended Writer Handoff

## 1. Что Уже Сделано

Текущий этап isolated extended writer закрыт следующими commits:

- `b8afbde feat: add isolated v0.2.1 extended writer`;
- `5ac1e5a test: verify extended writer merged ranges`;
- `afec382 test: fail closed on merged range changes`.

Push выполнен, GitHub Actions зелёный.

## 2. Текущее Назначение Isolated Extended Writer

`scripts/fill_invoice_quote_extended.py` - это изолированный минимальный writer
для первого безопасного code step расширенного Excel writer.

Текущее назначение:

- writer не имеет CLI;
- writer не подключён к `scripts/fill_invoice_quote_v0_2_separate.py`;
- writer не заменяет старый MVP `scripts/fill_invoice_quote_draft.py`;
- generated output остаётся черновиком;
- ручная проверка Excel обязательна перед любым использованием результата.

## 3. Что Умеет Текущий Writer

Текущий isolated extended writer умеет:

- принимать явную layout-модель `ExtendedLayout`;
- проверять layout/capacity fail-closed;
- проверять, что output создаётся вне Git-проекта;
- запрещать overwrite existing output;
- записывать 6+ позиций в тестовый extended template;
- писать через temp output;
- чистить temp/partial output при ошибке;
- делать snapshot/verify formulas;
- делать snapshot/verify header ranges;
- делать snapshot/verify signature range;
- делать snapshot/verify merged ranges;
- падать fail-closed при изменении merged ranges.

## 4. Что Покрыто Тестами

Текущие тесты покрывают:

- тестовый `.xlsx` создаётся кодом в `tmp_path`;
- 6 позиций успешно записываются;
- capacity overflow не создаёт output;
- existing output не перезаписывается;
- temp/partial output чистится при ошибке;
- conflicting layout падает fail-closed;
- старый MVP остаётся неизменным по SHA256;
- реальные `.xlsx` и manifest не попадают в Git changes;
- merged ranges сохраняются;
- изменение merged ranges приводит к ошибке и cleanup.

## 5. Что Пока НЕ Сделано

Пока не сделано:

- нет подключения к `scripts/fill_invoice_quote_v0_2_separate.py`;
- нет CLI;
- нет writer mode;
- нет manifest;
- нет dynamic row insertion;
- нет работы с реальным Excel-шаблоном;
- нет проверки drawing/media chain;
- нет использования output как клиентского КП.

## 6. Что Запрещено Без Отдельного Решения Игоря

Без отдельного решения Игоря запрещено:

- менять старый MVP `scripts/fill_invoice_quote_draft.py`;
- подключать extended writer к v0.2 separate layer;
- добавлять реальные `.xlsx` в Git;
- использовать реальный шаблон;
- включать dynamic row insertion;
- использовать generated output как клиентское КП;
- отправлять output клиенту;
- менять цену, срок, комплектацию или `project_spec`.

## 7. Рекомендуемые Следующие Варианты

Возможные следующие шаги, без реализации в этом handoff:

- усилить isolated writer негативными тестами по formulas/header/signature;
- отдельно спроектировать drawing/media chain snapshot;
- подготовить design/acceptance для подключения writer mode;
- только после этого думать о подключении к v0.2 separate layer.

## 8. Definition Of Done

Документ считается готовым, если:

- создан только один markdown-файл handoff;
- код не менялся;
- tests не менялись;
- `.xlsx` не добавлялись;
- manifest не создавался;
- старый MVP и v0.2 separate layer не трогались;
- `git diff --check` чистый;
- документ согласован до commit.

# Invoice Quote Filler v0.2.1 Handoff

## 1. Что Уже Сделано

Текущий этап v0.2.1 закрыт следующими commits:

- `71feff5 docs: add v0.2.1 template capacity plan`;
- `c1ddd32 docs: add v0.2.1 template capacity acceptance`;
- `3536fbf feat: add v0.2.1 template capacity guard`;
- `cedaa4c feat: add v0.2.1 template capacity option`;
- `e64e8d9 docs: add v0.2.1 extended writer design`.

Push выполнен, GitHub Actions зелёный.

## 2. Текущее Поведение

`--template-capacity` добавлен как явный preflight capacity source. Он нужен,
чтобы заранее проверить ёмкость шаблона до генерации output.

Default capacity остаётся `5`. Старый MVP
`scripts/fill_invoice_quote_draft.py` всё ещё ограничен 5 позициями и не должен
использоваться для записи за пределы своего проверенного диапазона.

Генерация 30-50 строк ещё не реализована. Если указать
`--template-capacity > 5`, это не должно автоматически обходить старый MVP и не
должно включать запись 30-50 строк без явного writer mode.

## 3. Что Запрещено Без Отдельного Решения Игоря

Без отдельного решения Игоря нельзя:

- менять старый MVP;
- снимать лимит 5;
- добавлять реальные `.xlsx` в Git;
- начинать динамическую вставку строк;
- считать generated output клиентским КП;
- отправлять generated output клиенту;
- менять цену, срок, комплектацию или `project_spec`.

## 4. Что Спроектировано

Спроектирован будущий `extended writer` для безопасной работы с заранее
подготовленным расширенным Excel-шаблоном.

Ключевые решения:

- extended writer должен быть отдельным будущим writer, а не неявным расширением
  старого MVP;
- в будущем можно добавить explicit writer mode, например
  `--writer mvp|extended`;
- extended writer должен включаться только при явном выборе;
- тестовый расширенный шаблон должен создаваться кодом в `tmp_path`;
- manifest и диагностика `inspect_excel_template.py` остаются будущими шагами,
  а не текущей реализацией.

## 5. Следующий Рекомендуемый Шаг

Следующий шаг после handoff - acceptance criteria для extended writer.

Это не code step. Acceptance criteria должны быть отдельным markdown-документом.
Только после согласования acceptance criteria можно обсуждать минимальный code
step с тестовым расширенным шаблоном в `tmp_path`.
